(() => {
  'use strict'

  const PAGE_SIZE = 100
  const STATIC_VERSION = '3.4.0-shell-1'
  const MATERIAL_NAMES = {
    P: 'Steel', M: 'Stainless steel', K: 'Cast iron', N: 'Non-ferrous',
    S: 'Heat-resistant alloys', H: 'Hardened materials', O: 'Other', unknown: 'Unknown'
  }
  const STATUS_LABELS = {
    manufacturer_verified: 'Manufacturer verified',
    catalog_verified: 'Catalog verified',
    shop_verified: 'Shop verified',
    source_located: 'Source located · not reviewed',
    legacy: 'Legacy · needs review',
    rejected: 'Rejected',
    needs_review: 'Needs review',
    accepted: 'Accepted',
    imported: 'Legacy import',
    catalog_claim: 'Catalog claim',
    manufacturer_claim: 'Manufacturer claim',
    unverified: 'Unverified',
    inferred: 'Inferred',
    pending: 'Pending review',
    verified: 'Human reviewed',
    quarantined: 'Quarantined',
    superseded: 'Superseded'
  }
  const STATUS_RANK = {
    manufacturer_verified: 5, catalog_verified: 4, shop_verified: 3,
    source_located: 2, legacy: 1, rejected: 0
  }
  const state = {
    index: null,
    tools: [],
    filtered: [],
    visible: PAGE_SIZE,
    selectedId: null,
    selectedGrade: null,
    selectedCondition: null,
    details: null,
    detailsPromise: null,
    toolMap: new Map(),
    outgoing: new Map(),
    incoming: new Map(),
    units: localStorage.getItem('toolbase-units') || 'source',
    theme: localStorage.getItem('toolbase-theme') || 'system'
  }

  const $ = selector => document.querySelector(selector)
  const elements = {
    search: $('#search-input'),
    manufacturer: $('#manufacturer-filter'),
    component: $('#component-filter'),
    material: $('#material-filter'),
    operation: $('#operation-filter'),
    geometry: $('#geometry-filter'),
    evidence: $('#evidence-filter'),
    cutting: $('#cutting-filter'),
    clear: $('#clear-filters'),
    filterButton: $('#filter-button'),
    filterPanel: $('#filter-panel'),
    filterCount: $('#filter-count'),
    count: $('#result-count'),
    summary: $('#query-summary'),
    list: $('#result-list'),
    more: $('#load-more'),
    detail: $('#detail-panel'),
    stats: $('#stats'),
    build: $('#build-label'),
    units: $('#unit-button'),
    theme: $('#theme-button'),
    offline: $('#offline-banner'),
    toast: $('#toast')
  }

  const escapeHtml = value => String(value ?? '')
    .replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;').replaceAll("'", '&#039;')
  const humanize = value => String(value || '').replaceAll('_', ' ').replace(/\b\w/g, letter => letter.toUpperCase())
  const normalize = value => String(value || '').toUpperCase().replace(/[^A-Z0-9]/g, '')
  const statusLabel = value => STATUS_LABELS[value] || humanize(value)
  const statusClass = value => escapeHtml(String(value || 'legacy').replaceAll('_', '-'))
  const count = value => Number(value || 0).toLocaleString()
  const safeUrl = value => /^https?:\/\//i.test(String(value || '')) ? value : null
  const unique = values => [...new Set(values.filter(Boolean))]
  const rounded = value => Number(Number(value).toPrecision(4)).toLocaleString(undefined, { maximumFractionDigits: 4 })

  function showToast(message) {
    elements.toast.textContent = message
    elements.toast.hidden = false
    clearTimeout(showToast.timer)
    showToast.timer = setTimeout(() => { elements.toast.hidden = true }, 2400)
  }

  function badge(status, label = statusLabel(status)) {
    return `<span class="badge ${statusClass(status)}">${escapeHtml(label)}</span>`
  }

  function applyTheme() {
    document.documentElement.dataset.theme = state.theme
    elements.theme.textContent = `Theme: ${humanize(state.theme)}`
  }

  function cycleTheme() {
    const values = ['system', 'light', 'dark']
    state.theme = values[(values.indexOf(state.theme) + 1) % values.length]
    localStorage.setItem('toolbase-theme', state.theme)
    applyTheme()
  }

  function applyUnits() {
    elements.units.textContent = state.units === 'source' ? 'Source units' : state.units === 'metric' ? 'Metric' : 'Inch'
    if (state.selectedId && state.details) renderDetail()
  }

  function cycleUnits() {
    const values = ['source', 'metric', 'inch']
    state.units = values[(values.indexOf(state.units) + 1) % values.length]
    localStorage.setItem('toolbase-units', state.units)
    applyUnits()
    showToast(`Showing ${elements.units.textContent.toLowerCase()}`)
  }

  function readUrlState() {
    const params = new URLSearchParams(location.search)
    const fields = {
      q: elements.search,
      maker: elements.manufacturer,
      type: elements.component,
      material: elements.material,
      operation: elements.operation,
      geometry: elements.geometry,
      evidence: elements.evidence,
      cutting: elements.cutting
    }
    for (const [name, element] of Object.entries(fields)) {
      if (params.has(name)) element.value = params.get(name)
    }
    state.selectedGrade = params.get('grade') || null
    state.selectedCondition = params.get('condition') || null
    return decodeURIComponent(location.hash.replace(/^#tool=/, '')) || null
  }

  function writeUrl({ push = false, selected = state.selectedId } = {}) {
    const params = new URLSearchParams()
    const values = {
      q: elements.search.value.trim(), maker: elements.manufacturer.value,
      type: elements.component.value, material: elements.material.value,
      operation: elements.operation.value, geometry: elements.geometry.value,
      evidence: elements.evidence.value, cutting: elements.cutting.value
    }
    for (const [name, value] of Object.entries(values)) if (value) params.set(name, value)
    if (state.selectedGrade) params.set('grade', state.selectedGrade)
    if (state.selectedCondition) params.set('condition', state.selectedCondition)
    const query = params.toString()
    const hash = selected ? `#tool=${encodeURIComponent(selected)}` : ''
    const url = `${location.pathname}${query ? `?${query}` : ''}${hash}`
    history[push ? 'pushState' : 'replaceState']({ tool: selected }, '', url)
  }

  function option(value, label, itemCount) {
    return `<option value="${escapeHtml(value)}">${escapeHtml(label)} (${count(itemCount)})</option>`
  }

  function addOptions(element, values, label = humanize) {
    element.insertAdjacentHTML('beforeend', [...values.entries()]
      .sort((a, b) => String(a[0]).localeCompare(String(b[0])))
      .map(([value, itemCount]) => option(value, label(value), itemCount)).join(''))
  }

  function populateFilters() {
    const buckets = {
      manufacturer: new Map(), component: new Map(), material: new Map(),
      operation: new Map(), geometry: new Map(), evidence: new Map()
    }
    const bump = (bucket, value) => { if (value) bucket.set(value, (bucket.get(value) || 0) + 1) }
    state.tools.forEach(tool => {
      bump(buckets.manufacturer, tool.manufacturer)
      bump(buckets.component, tool.component_type)
      bump(buckets.geometry, tool.geometry_shape)
      bump(buckets.evidence, tool.verification_status)
      unique(tool.material_groups).forEach(value => bump(buckets.material, value))
      unique(tool.operation_types).forEach(value => bump(buckets.operation, value))
    })
    addOptions(elements.manufacturer, buckets.manufacturer, value => value)
    addOptions(elements.component, buckets.component)
    addOptions(elements.material, buckets.material, value => `${value} · ${MATERIAL_NAMES[value] || value}`)
    addOptions(elements.operation, buckets.operation)
    addOptions(elements.geometry, buckets.geometry, value => value)
    addOptions(elements.evidence, buckets.evidence, statusLabel)
  }

  function renderStats() {
    const mapped = state.tools.filter(tool => tool.material_groups.length).length
    const verified = state.index.meta.counts.cutting_data_profiles || 0
    const reviewed = state.tools.filter(tool => ['manufacturer_verified', 'catalog_verified', 'shop_verified'].includes(tool.verification_status)).length
    const values = [
      ['Tools', state.tools.length], ['Verified cutting profiles', verified],
      ['Material mapped', mapped], ['Review status', `${reviewed} reviewed`]
    ]
    elements.stats.innerHTML = values.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(count(value) === '0' && typeof value === 'string' ? value : typeof value === 'number' ? count(value) : value)}</dd></div>`).join('')
    elements.build.textContent = `Schema ${state.index.meta.schema_version} · build ${state.index.meta.build_hash}`
  }

  function scoreTool(tool, terms, normalizedQuery) {
    if (!terms.length) return 0
    if (!terms.every(term => tool.search_text.includes(term))) return -1
    let score = 100
    if (normalize(tool.part_number) === normalizedQuery) score += 10000
    else if (tool.aliases.some(alias => normalize(alias) === normalizedQuery)) score += 9000
    else if (normalize(tool.part_number).startsWith(normalizedQuery)) score += 5000
    else if (tool.aliases.some(alias => normalize(alias).startsWith(normalizedQuery))) score += 4200
    if (tool.part_number.toLocaleLowerCase().includes(terms[0])) score += 800
    score += (STATUS_RANK[tool.verification_status] || 0) * 20
    return score
  }

  function activeFilterCount() {
    return [elements.manufacturer, elements.component, elements.material, elements.operation,
      elements.geometry, elements.evidence, elements.cutting].filter(element => element.value).length
  }

  function applyFilters({ sync = true } = {}) {
    const query = elements.search.value.trim().toLocaleLowerCase()
    const terms = query.split(/\s+/).filter(Boolean)
    const normalizedQuery = normalize(query)
    state.filtered = state.tools.map(tool => ({ tool, score: scoreTool(tool, terms, normalizedQuery) }))
      .filter(item => item.score >= 0)
      .filter(({ tool }) => !elements.manufacturer.value || tool.manufacturer === elements.manufacturer.value)
      .filter(({ tool }) => !elements.component.value || tool.component_type === elements.component.value)
      .filter(({ tool }) => !elements.material.value || tool.material_groups.includes(elements.material.value))
      .filter(({ tool }) => !elements.operation.value || tool.operation_types.includes(elements.operation.value))
      .filter(({ tool }) => !elements.geometry.value || tool.geometry_shape === elements.geometry.value)
      .filter(({ tool }) => !elements.evidence.value || tool.verification_status === elements.evidence.value)
      .filter(({ tool }) => elements.cutting.value !== 'yes' || tool.has_cutting_data)
      .filter(({ tool }) => elements.cutting.value !== 'no' || !tool.has_cutting_data)
      .sort((a, b) => b.score - a.score ||
        (STATUS_RANK[b.tool.verification_status] || 0) - (STATUS_RANK[a.tool.verification_status] || 0) ||
        a.tool.part_number.localeCompare(b.tool.part_number))
      .map(item => item.tool)
    state.visible = PAGE_SIZE
    const filters = activeFilterCount()
    elements.filterCount.textContent = filters
    elements.summary.textContent = query ? `for “${query}”` : ''
    renderList()
    if (sync) writeUrl()
  }

  function rowMarkup(tool) {
    const groups = tool.material_groups.slice(0, 4).map(group => `<span class="material-chip" title="${escapeHtml(MATERIAL_NAMES[group] || group)}">${escapeHtml(group)}</span>`).join('')
    const reviewBadge = tool.review_status === 'quarantined'
      ? badge('quarantined')
      : tool.review_status === 'verified' ? badge('verified') : ''
    return `<button class="tool-row${tool.id === state.selectedId ? ' selected' : ''}" type="button" data-tool-id="${escapeHtml(tool.id)}" aria-pressed="${tool.id === state.selectedId}">
      <span class="tool-main"><strong>${escapeHtml(tool.part_number)}</strong><small>${escapeHtml(tool.description)}</small></span>
      <span class="row-maker">${escapeHtml(tool.manufacturer)}</span>
      <span class="row-meta">${reviewBadge}${badge(tool.verification_status)}<span class="badge">${escapeHtml(humanize(tool.component_type))}</span>${groups}${tool.has_cutting_data ? '<span class="badge catalog-verified">Cutting data</span>' : ''}</span>
    </button>`
  }

  function renderList() {
    elements.list.setAttribute('aria-busy', 'false')
    elements.count.textContent = count(state.filtered.length)
    if (!state.filtered.length) {
      elements.list.innerHTML = '<div class="empty-results"><strong>No matching tools</strong><p>Try a part-number fragment or clear a filter.</p></div>'
      elements.more.hidden = true
      return
    }
    elements.list.innerHTML = state.filtered.slice(0, state.visible).map(rowMarkup).join('')
    elements.more.hidden = state.visible >= state.filtered.length
    elements.more.textContent = `Show ${Math.min(PAGE_SIZE, state.filtered.length - state.visible)} more`
  }

  async function loadDetails() {
    if (state.details) return state.details
    if (!state.detailsPromise) {
      state.detailsPromise = fetch(`./data/catalog-details.json?v=${STATIC_VERSION}`, { cache: 'no-cache' })
        .then(response => {
          if (!response.ok) throw new Error(`Detail bundle returned HTTP ${response.status}`)
          return response.json()
        })
        .then(data => {
          state.details = data
          state.toolMap = new Map(Object.entries(data.tools_by_id))
          for (const relationship of data.relationships) {
            if (!state.outgoing.has(relationship.subject_tool_id)) state.outgoing.set(relationship.subject_tool_id, [])
            state.outgoing.get(relationship.subject_tool_id).push(relationship)
            if (relationship.object_tool_id) {
              if (!state.incoming.has(relationship.object_tool_id)) state.incoming.set(relationship.object_tool_id, [])
              state.incoming.get(relationship.object_tool_id).push(relationship)
            }
          }
          return data
        })
    }
    return state.detailsPromise
  }

  async function selectTool(id, { push = true, scroll = true, preserveDetailFilters = false } = {}) {
    if (!state.tools.some(tool => tool.id === id)) return
    if (state.selectedId !== id && !preserveDetailFilters) {
      state.selectedGrade = null
      state.selectedCondition = null
    }
    state.selectedId = id
    renderList()
    elements.detail.classList.add('open')
    elements.detail.setAttribute('aria-hidden', 'false')
    document.body.classList.add('detail-open')
    elements.detail.innerHTML = '<div class="loading"><span></span><p>Loading source-backed details…</p></div>'
    writeUrl({ push, selected: id })
    try {
      await loadDetails()
      renderDetail()
      if (scroll) elements.detail.scrollTop = 0
    } catch (error) {
      elements.detail.innerHTML = `<div class="error-state"><strong>Tool details could not be loaded.</strong><p>${escapeHtml(error.message)}</p></div>`
    }
  }

  function closeDetail({ push = true } = {}) {
    state.selectedId = null
    state.selectedGrade = null
    state.selectedCondition = null
    elements.detail.classList.remove('open')
    elements.detail.setAttribute('aria-hidden', 'true')
    document.body.classList.remove('detail-open')
    renderList()
    writeUrl({ push, selected: null })
  }

  function factValue(fact) {
    let value = fact.value
    if (Array.isArray(value)) value = value.join(', ')
    else if (value && typeof value === 'object') value = JSON.stringify(value)
    else if (typeof value === 'boolean') value = value ? 'Yes' : 'No'
    return `${value ?? '—'}${fact.unit ? ` ${fact.unit}` : ''}`
  }

  function specGrid(tool) {
    const specs = [
      ['Component', humanize(tool.component_type)], ['Family', tool.family], ['Tool type', tool.tool_type],
      ['Size', tool.size], ['Geometry', tool.geometry], ['Insert seat', tool.insert_seat],
      ['ISO designation', tool.iso_designation], ['Grade', tool.grade], ['Shape', tool.shape],
      ['Chipbreaker', tool.chipbreaker], ['Lifecycle', humanize(tool.lifecycle_status)]
    ].filter(([, value]) => value)
    return specs.length ? `<dl class="spec-grid">${specs.map(([label, value]) => `<div><dt>${escapeHtml(label)}</dt><dd>${escapeHtml(value)}</dd></div>`).join('')}</dl>`
      : emptyData('No normalized specifications', 'Legacy facts, if present, remain available in the audit section.')
  }

  function geometrySvg(geometry) {
    const code = geometry.shape_code
    if (code === 'R') return '<circle class="insert-shape" cx="90" cy="85" r="68"/><circle class="insert-hole" cx="90" cy="85" r="20"/>'
    const points = {
      T: '90,10 170,155 10,155',
      S: '25,20 155,20 155,150 25,150',
      C: '90,10 168,85 90,160 12,85',
      D: '90,8 151,85 90,162 29,85',
      V: '90,6 129,85 90,164 51,85',
      W: '90,10 160,47 146,130 90,160 34,130 20,47',
      L: '18,35 162,35 162,135 18,135'
    }[code] || '30,20 150,20 165,145 15,145'
    return `<polygon class="insert-shape" points="${points}"/>${geometry.style_code && geometry.style_code !== 'N' ? '<circle class="insert-hole" cx="90" cy="85" r="20"/>' : ''}`
  }

  function geometrySection(tool) {
    const geometry = tool.geometry_display
    if (!geometry) return emptyData('No normalized geometry yet', 'The database does not contain enough structured geometry to draw this tool without guessing.')
    const decodeStatus = geometry.designation_verification_status || 'legacy'
    const lines = [
      { label: 'ISO designation', value: geometry.designation, status: decodeStatus },
      { label: 'Shape', value: [geometry.shape_code, geometry.shape_name, geometry.included_angle].filter(Boolean).join(' · '), status: decodeStatus },
      { label: 'Clearance', value: [geometry.clearance_code, geometry.clearance].filter(Boolean).join(' · '), status: decodeStatus },
      { label: 'Tolerance code', value: geometry.tolerance_code, status: decodeStatus },
      { label: 'Insert style code', value: geometry.style_code, status: decodeStatus },
      ...geometry.dimensions.map(item => ({ label: item.label, value: `${item.value}${item.unit ? ` ${item.unit}` : ''}`, status: item.verification_status }))
    ].filter(item => item.value)
    return `<div class="geometry-card">
      <div class="geometry-figure"><svg viewBox="0 0 180 170" role="img" aria-label="Normalized ${escapeHtml(geometry.shape_name || 'insert')} schematic">${geometrySvg(geometry)}</svg></div>
      <div><div class="geometry-data">${lines.map(item => `<div class="geometry-line"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong>${badge(item.status)}</div>`).join('')}</div><p class="geometry-note">${escapeHtml(geometry.note)} ISO letter meanings are decoded from the designation; dimensional rows keep their own evidence status.</p></div>
    </div>`
  }

  function emptyData(title, message) {
    return `<div class="empty-data"><strong>${escapeHtml(title)}</strong>${escapeHtml(message)}</div>`
  }

  function auditSummary(item) {
    return [item.source_page_ref, item.source_table_ref, item.reviewer && `reviewed by ${item.reviewer}`, item.reviewed_at].filter(Boolean).join(' · ')
  }

  function gradeOptions(tool) {
    const bestByCode = new Map()
    for (const option of tool.grade_options || []) {
      const current = bestByCode.get(option.code)
      if (!current || (STATUS_RANK[option.verification_status] || 0) > (STATUS_RANK[current.verification_status] || 0)) {
        bestByCode.set(option.code, option)
      }
    }
    for (const profile of tool.cutting_data || []) {
      if (profile.source_grade && !bestByCode.has(profile.source_grade)) {
        bestByCode.set(profile.source_grade, { code: profile.source_grade, verification_status: profile.verification_status })
      }
    }
    return [...bestByCode.values()].sort((a, b) =>
      Number(Boolean(b.is_primary)) - Number(Boolean(a.is_primary)) || a.code.localeCompare(b.code))
  }

  function detailSelectors(tool) {
    const grades = gradeOptions(tool)
    const conditions = unique((tool.cutting_data || []).map(profile => profile.cut_condition)).sort()
    if (state.selectedGrade && !grades.some(option => option.code === state.selectedGrade)) state.selectedGrade = null
    if (state.selectedCondition && !conditions.includes(state.selectedCondition)) state.selectedCondition = null
    if (!grades.length && !conditions.length) return ''
    const gradeSelect = grades.length ? `<label>Grade<select data-detail-grade><option value="">All listed grades</option>${grades.map(option => `<option value="${escapeHtml(option.code)}"${state.selectedGrade === option.code ? ' selected' : ''}>${escapeHtml(option.code)} · ${escapeHtml(statusLabel(option.verification_status))}</option>`).join('')}</select></label>` : ''
    const conditionSelect = conditions.length ? `<label>Cut condition<select data-detail-condition><option value="">All conditions</option>${conditions.map(condition => `<option value="${escapeHtml(condition)}"${state.selectedCondition === condition ? ' selected' : ''}>${escapeHtml(humanize(condition))}</option>`).join('')}</select></label>` : ''
    return `<div class="detail-selectors">${gradeSelect}${conditionSelect}</div>`
  }

  function filteredMaterials(tool) {
    if (!state.selectedGrade) return tool.materials
    return tool.materials.filter(item => item.grade_code === state.selectedGrade)
  }

  function filteredProfiles(tool) {
    return tool.cutting_data.filter(profile =>
      (!state.selectedGrade || profile.source_grade === state.selectedGrade) &&
      (!state.selectedCondition || profile.cut_condition === state.selectedCondition))
  }

  function materialSection(tool) {
    const materials = filteredMaterials(tool)
    if (!materials.length) return emptyData('No verified work-material recommendation for this selection', 'Tags, legacy material fields, and grade descriptions are never promoted to recommendations without an exact reviewed manufacturer source.')
    return `<div class="material-list">${materials.map(item => `<article class="material-row">
      <span class="material-chip">ISO ${escapeHtml(item.iso_group)}</span>
      <p><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml([item.grade_code, item.material_subgroup || 'Subgroup not specified', humanize(item.suitability)].filter(Boolean).join(' · '))}</small>${auditSummary(item) ? `<small>${escapeHtml(auditSummary(item))}</small>` : ''}${item.notes ? `<small>${escapeHtml(item.notes)}</small>` : ''}</p>
      ${badge(item.verification_status)}
    </article>`).join('')}</div>`
  }

  function unreviewedMaterialSection(tool) {
    const claims = tool.unreviewed_material_claims || []
    if (!claims.length) return ''
    return `<details class="legacy-claims"><summary>${claims.length} unreviewed legacy material claim${claims.length === 1 ? '' : 's'}</summary><p>These values are retained for audit only. They do not power search filters and are not recommendations.</p><div class="material-list">${claims.map(item => `<article class="material-row"><span class="material-chip">ISO ${escapeHtml(item.iso_group)}</span><p><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml(item.material_subgroup || 'Subgroup not specified')}</small></p>${badge(item.verification_status)}</article>`).join('')}</div></details>`
  }

  function convertValue(value, unit, target) {
    if (value == null) return { value: null, unit, converted: false }
    if (target === 'source') return { value, unit, converted: false }
    if (unit === 'm_per_min') return target === 'inch' ? { value: value * 3.28084, unit: 'sfm', converted: true } : { value, unit: 'm/min', converted: false }
    if (unit === 'sfm') return target === 'metric' ? { value: value / 3.28084, unit: 'm/min', converted: true } : { value, unit: 'sfm', converted: false }
    if (unit === 'mm_per_rev') return target === 'inch' ? { value: value / 25.4, unit: 'ipr', converted: true } : { value, unit: 'mm/rev', converted: false }
    if (unit === 'ipr') return target === 'metric' ? { value: value * 25.4, unit: 'mm/rev', converted: true } : { value, unit: 'ipr', converted: false }
    if (unit === 'mm') return target === 'inch' ? { value: value / 25.4, unit: 'in', converted: true } : { value, unit: 'mm', converted: false }
    if (unit === 'in') return target === 'metric' ? { value: value * 25.4, unit: 'mm', converted: true } : { value, unit: 'in', converted: false }
    return { value, unit: humanize(unit), converted: false }
  }

  function rangeMarkup(min, max, unit) {
    const a = convertValue(min, unit, state.units)
    const b = convertValue(max, unit, state.units)
    if (a.value == null && b.value == null) return '—'
    const values = a.value != null && b.value != null ? `${rounded(a.value)}–${rounded(b.value)}` : rounded(a.value ?? b.value)
    return `${values} ${a.unit}${a.converted || b.converted ? ' (converted)' : ''}`
  }

  function speedStart(profile) {
    const value = convertValue(profile.surface_speed_start, profile.surface_speed_unit, state.units)
    return value.value == null ? '' : `${rounded(value.value)} ${value.unit}${value.converted ? ' (converted)' : ''}`
  }

  function calculatorUnit(profile) {
    if (state.units === 'inch') return 'in'
    if (state.units === 'metric') return 'mm'
    return profile.surface_speed_unit === 'sfm' ? 'in' : 'mm'
  }

  function cuttingSection(tool) {
    const profiles = filteredProfiles(tool)
    if (!profiles.length) return emptyData('No manufacturer-verified speeds and feeds for this selection', 'Nothing is estimated from a similar insert. Values appear only after the exact part, grade, geometry, material subgroup, and source table are reviewed.')
    return profiles.map(profile => `<article class="cutting-profile" data-profile-id="${escapeHtml(profile.id)}">
      <div class="cutting-head"><strong>ISO ${escapeHtml(profile.iso_material_group)}${profile.material_subgroup ? ` · ${escapeHtml(profile.material_subgroup)}` : ''} · ${escapeHtml(humanize(profile.operation_type))}</strong>${badge(profile.verification_status)}</div>
      <p class="cutting-context">${escapeHtml([profile.source_material_label, profile.source_grade, profile.source_chipbreaker, humanize(profile.cut_condition)].filter(Boolean).join(' · '))}</p>
      <div class="cutting-values">
        <div><span>Surface speed</span><b>${escapeHtml(rangeMarkup(profile.surface_speed_min, profile.surface_speed_max, profile.surface_speed_unit))}</b>${speedStart(profile) ? `<small>Start: ${escapeHtml(speedStart(profile))}</small>` : ''}</div>
        <div><span>Feed per revolution</span><b>${escapeHtml(rangeMarkup(profile.feed_min, profile.feed_max, profile.feed_unit))}</b></div>
        <div><span>Depth of cut</span><b>${escapeHtml(rangeMarkup(profile.depth_of_cut_min, profile.depth_of_cut_max, profile.depth_of_cut_unit))}</b></div>
      </div>
      <div class="calculator"><label>Stock diameter (${calculatorUnit(profile)})<input type="number" inputmode="decimal" min="0" step="any" data-calc-profile="${escapeHtml(profile.id)}" placeholder="Enter diameter"></label><p class="calculator-output" data-calc-output="${escapeHtml(profile.id)}">Uses the manufacturer start speed; the calculated RPM is not stored as source data.</p></div>
      <p class="audit-line">${escapeHtml(auditSummary(profile) || 'Source location not recorded')}</p>
      <details class="audit-details"><summary>Show source excerpt and review notes</summary>${profile.source_raw_text ? `<p>${escapeHtml(profile.source_raw_text)}</p>` : ''}${profile.notes ? `<p>${escapeHtml(profile.notes)}</p>` : ''}</details>
    </article>`).join('')
  }

  function calculateProfile(profileId, diameterValue) {
    const tool = state.toolMap.get(state.selectedId)
    const profile = tool?.cutting_data.find(item => item.id === profileId)
    const output = elements.detail.querySelector(`[data-calc-output="${CSS.escape(profileId)}"]`)
    const diameter = Number(diameterValue)
    if (!profile || !output || !(diameter > 0)) {
      if (output) output.textContent = 'Uses the manufacturer start speed; the calculated RPM is not stored as source data.'
      return
    }
    const sourceSpeed = profile.surface_speed_start ?? ((profile.surface_speed_min + profile.surface_speed_max) / 2)
    const useInch = calculatorUnit(profile) === 'in'
    const speed = profile.surface_speed_unit === 'sfm' ? sourceSpeed : sourceSpeed * 3.28084
    const diameterIn = useInch ? diameter : diameter / 25.4
    const rpm = (12 * speed) / (Math.PI * diameterIn)
    const feedMinIpr = profile.feed_unit === 'ipr' ? profile.feed_min : profile.feed_min / 25.4
    const feedMaxIpr = profile.feed_unit === 'ipr' ? profile.feed_max : profile.feed_max / 25.4
    const feedMin = useInch ? rpm * feedMinIpr : rpm * feedMinIpr * 25.4
    const feedMax = useInch ? rpm * feedMaxIpr : rpm * feedMaxIpr * 25.4
    output.textContent = `${Math.round(rpm).toLocaleString()} RPM at start speed · feed-rate window ${rounded(feedMin)}–${rounded(feedMax)} ${useInch ? 'in/min' : 'mm/min'} (calculated)`
  }

  function relationshipTarget(relationship, incoming) {
    const id = incoming ? relationship.subject_tool_id : relationship.object_tool_id
    return id ? state.toolMap.get(id) : null
  }

  function compatibilitySection(tool) {
    const relationships = [
      ...(state.outgoing.get(tool.id) || []).map(item => ({ item, incoming: false })),
      ...(state.incoming.get(tool.id) || []).map(item => ({ item, incoming: true }))
    ].filter(({ item }) => !item.suppressed)
    if (!relationships.length) return emptyData('No compatibility claim recorded', 'Absence of a relationship is not proof that two tools do or do not fit.')
    return `<div class="relationship-list">${relationships.map(({ item, incoming }) => {
      const target = relationshipTarget(item, incoming)
      const title = target?.part_number || item.object_value || 'External interface'
      const direction = incoming ? `${humanize(item.relationship)} this tool` : humanize(item.relationship)
      const status = item.review_status === 'accepted' ? item.evidence_status : item.review_status
      const body = `<span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(direction)} · ${escapeHtml(item.notes || 'No notes')}</small></span>${badge(status)}`
      return target ? `<button class="relationship" type="button" data-tool-id="${escapeHtml(target.id)}">${body}</button>` : `<div class="relationship">${body}</div>`
    }).join('')}</div>`
  }

  function sourceIdsFor(tool) {
    const ids = [...tool.source_ids]
    tool.facts.forEach(item => ids.push(...item.source_ids))
    tool.materials.forEach(item => ids.push(...item.source_ids))
    ;(tool.unreviewed_material_claims || []).forEach(item => ids.push(...item.source_ids))
    ;(tool.grade_options || []).forEach(item => ids.push(item.source_id))
    tool.cutting_data.forEach(item => ids.push(item.source_id))
    ;[...(state.outgoing.get(tool.id) || []), ...(state.incoming.get(tool.id) || [])].forEach(item => {
      ids.push(item.source_id)
      ;(item.source_refs || []).forEach(ref => ids.push(ref.source_id))
    })
    return unique(ids)
  }

  function sourceSection(tool) {
    const sources = sourceIdsFor(tool).map(id => state.details.sources_by_id[id]).filter(Boolean)
    if (!sources.length) return emptyData('No source linked', 'This legacy record needs a manufacturer source before its specifications can be audited.')
    return `<div class="source-list">${sources.map(source => {
      const link = safeUrl(source.url)
      const location = [source.page_ref, source.document_edition, source.retrieved_at && `retrieved ${source.retrieved_at}`].filter(Boolean).join(' · ')
      return `<article class="source-card">${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a>` : `<strong>${escapeHtml(source.title)}</strong>`}<p>${escapeHtml(humanize(source.source_type))}${location ? ` · ${escapeHtml(location)}` : ''}</p>${source.content_sha256 ? `<p><code>SHA-256 ${escapeHtml(source.content_sha256)}</code></p>` : ''}${source.local_path ? `<p>Local audit file: <code>${escapeHtml(source.local_path)}</code> (not published)</p>` : ''}${source.notes ? `<p>${escapeHtml(source.notes)}</p>` : ''}</article>`
    }).join('')}</div>`
  }

  function factsSection(tool) {
    if (!tool.facts.length) return emptyData('No additional facts', 'No legacy or reviewed fact rows are attached to this tool.')
    const current = `<div class="fact-list">${tool.facts.map(fact => `<article class="fact-card"><strong>${escapeHtml(humanize(fact.original_key || fact.key))}</strong><span>${escapeHtml(factValue(fact))}</span>${badge(fact.verification_status)}${auditSummary(fact) ? `<small>${escapeHtml(auditSummary(fact))}</small>` : ''}</article>`).join('')}</div>`
    const history = tool.fact_history?.length ? `<details class="audit-history"><summary>${tool.fact_history.length} superseded fact${tool.fact_history.length === 1 ? '' : 's'}</summary><div class="fact-list">${tool.fact_history.map(fact => `<article class="fact-card"><strong>${escapeHtml(humanize(fact.original_key || fact.key))}</strong><span>${escapeHtml(factValue(fact))}</span>${badge(fact.verification_status)}</article>`).join('')}</div></details>` : ''
    return current + history
  }

  function detailSection(title, content, meta = '') {
    return `<section class="detail-section"><div class="section-heading"><h3>${escapeHtml(title)}</h3>${meta ? `<span>${escapeHtml(meta)}</span>` : ''}</div>${content}</section>`
  }

  function renderDetail() {
    const tool = state.toolMap.get(state.selectedId)
    if (!tool) return
    const relationshipCount = (state.outgoing.get(tool.id)?.length || 0) + (state.incoming.get(tool.id)?.length || 0)
    const selectors = detailSelectors(tool)
    const materials = filteredMaterials(tool)
    const profiles = filteredProfiles(tool)
    const quarantine = tool.review_status === 'quarantined' ? `<div class="quarantine-banner"><strong>Quarantined record</strong><p>${escapeHtml(tool.quarantine_reason || 'The exact identity or source support was rejected during review. Recommendations are suppressed.')}</p></div>` : ''
    elements.detail.innerHTML = `
      <div class="mobile-detail-bar"><button class="back-button" type="button" data-close-detail>← Results</button></div>
      <header class="detail-header"><div class="detail-kicker"><span>${escapeHtml(humanize(tool.component_type))}</span><span>${tool.review_status === 'verified' ? badge('verified') : tool.review_status === 'quarantined' ? badge('quarantined') : badge(tool.verification_status)}</span></div><h2>${escapeHtml(tool.part_number)}</h2><p class="detail-maker">${escapeHtml(tool.manufacturer)}</p><p class="detail-description">${escapeHtml(tool.description)}</p>${selectors}</header>
      ${quarantine}
      ${detailSection('Core specifications', specGrid(tool))}
      ${detailSection('Geometry', geometrySection(tool))}
      ${detailSection('Recommended work materials', materialSection(tool) + unreviewedMaterialSection(tool), `${materials.length} verified`)}
      ${detailSection('Speeds and feeds', cuttingSection(tool), `${profiles.length} verified`)}
      ${detailSection('Compatibility path', compatibilitySection(tool), `${relationshipCount} claims`)}
      ${detailSection('Sources and audit trail', sourceSection(tool), `${sourceIdsFor(tool).length} sources`)}
      ${detailSection('Additional facts', factsSection(tool), `${tool.facts.length} facts`)}
    `
  }

  function clearFilters() {
    elements.search.value = ''
    ;[elements.manufacturer, elements.component, elements.material, elements.operation,
      elements.geometry, elements.evidence, elements.cutting].forEach(element => { element.value = '' })
    applyFilters()
  }

  function setOfflineStatus() {
    elements.offline.hidden = navigator.onLine
  }

  function wireEvents() {
    let timer
    elements.search.addEventListener('input', () => {
      clearTimeout(timer)
      timer = setTimeout(() => applyFilters(), 90)
    })
    ;[elements.manufacturer, elements.component, elements.material, elements.operation,
      elements.geometry, elements.evidence, elements.cutting].forEach(element => element.addEventListener('change', () => applyFilters()))
    elements.clear.addEventListener('click', clearFilters)
    elements.more.addEventListener('click', () => { state.visible += PAGE_SIZE; renderList() })
    elements.filterButton.addEventListener('click', () => {
      const open = elements.filterPanel.classList.toggle('open')
      elements.filterButton.setAttribute('aria-expanded', String(open))
    })
    elements.units.addEventListener('click', cycleUnits)
    elements.theme.addEventListener('click', cycleTheme)
    document.addEventListener('keydown', event => {
      if (event.key === '/' && !/INPUT|SELECT|TEXTAREA/.test(document.activeElement.tagName)) {
        event.preventDefault(); elements.search.focus()
      }
      if (event.key === 'Escape' && state.selectedId && matchMedia('(max-width: 760px)').matches) closeDetail()
    })
    elements.list.addEventListener('click', event => {
      const button = event.target.closest('[data-tool-id]')
      if (button) selectTool(button.dataset.toolId)
    })
    elements.detail.addEventListener('click', event => {
      if (event.target.closest('[data-close-detail]')) closeDetail()
      const button = event.target.closest('[data-tool-id]')
      if (button) selectTool(button.dataset.toolId)
    })
    elements.detail.addEventListener('input', event => {
      const input = event.target.closest('[data-calc-profile]')
      if (input) calculateProfile(input.dataset.calcProfile, input.value)
    })
    elements.detail.addEventListener('change', event => {
      if (event.target.matches('[data-detail-grade]')) {
        state.selectedGrade = event.target.value || null
        renderDetail()
        writeUrl()
      }
      if (event.target.matches('[data-detail-condition]')) {
        state.selectedCondition = event.target.value || null
        renderDetail()
        writeUrl()
      }
    })
    window.addEventListener('online', setOfflineStatus)
    window.addEventListener('offline', setOfflineStatus)
    window.addEventListener('popstate', () => {
      const params = new URLSearchParams(location.search)
      state.selectedGrade = params.get('grade') || null
      state.selectedCondition = params.get('condition') || null
      const selected = decodeURIComponent(location.hash.replace(/^#tool=/, '')) || null
      if (selected) selectTool(selected, { push: false, scroll: false, preserveDetailFilters: true })
      else closeDetail({ push: false })
    })
  }

  async function initialize() {
    applyTheme()
    applyUnits()
    setOfflineStatus()
    wireEvents()
    try {
      const response = await fetch(`./data/catalog-index.json?v=${STATIC_VERSION}`, { cache: 'no-cache' })
      if (!response.ok) throw new Error(`Search index returned HTTP ${response.status}`)
      state.index = await response.json()
      state.tools = state.index.tools
      populateFilters()
      renderStats()
      const selected = readUrlState()
      applyFilters({ sync: false })
      writeUrl({ selected })
      if (selected) await selectTool(selected, { push: false, preserveDetailFilters: true })
      if ('serviceWorker' in navigator && location.protocol.startsWith('http')) {
        navigator.serviceWorker.register('./sw.js').catch(() => {})
      }
    } catch (error) {
      elements.list.setAttribute('aria-busy', 'false')
      elements.list.innerHTML = `<div class="error-state"><strong>The catalog could not be loaded.</strong><p>${escapeHtml(error.message)}</p></div>`
      elements.build.textContent = 'Index unavailable'
    }
  }

  initialize()
})()
