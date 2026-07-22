(() => {
  'use strict'

  const PAGE_SIZE = 100
  const STATIC_VERSION = '3.4.0-shell-5'
  const MATERIAL_NAMES = {
    P: 'Steel', M: 'Stainless steel', K: 'Cast iron', N: 'Non-ferrous',
    S: 'Heat-resistant alloys', H: 'Hardened materials', O: 'Other', unknown: 'Unknown'
  }
  const SOURCE_UNIT_LABELS = {
    m_per_min: 'm/min', mm_per_rev: 'mm/rev', mm_per_tooth: 'mm/tooth',
    mm_per_min: 'mm/min', sfm: 'sfm', ipr: 'ipr', ipt: 'ipt', mm: 'mm', in: 'in'
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
  const count = value => Number(value || 0).toLocaleString()
  const safeUrl = value => /^https?:\/\//i.test(String(value || '')) ? value : null
  const unique = values => [...new Set(values.filter(Boolean))]
  const rounded = value => Number(Number(value).toPrecision(4)).toLocaleString(undefined, { maximumFractionDigits: 4 })
  const sourceUnitLabel = unit => SOURCE_UNIT_LABELS[unit] || humanize(unit)

  function showToast(message) {
    elements.toast.textContent = message
    elements.toast.hidden = false
    clearTimeout(showToast.timer)
    showToast.timer = setTimeout(() => { elements.toast.hidden = true }, 2400)
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
      cutting: elements.cutting.value
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
      operation: new Map(), geometry: new Map()
    }
    const bump = (bucket, value) => { if (value) bucket.set(value, (bucket.get(value) || 0) + 1) }
    state.tools.forEach(tool => {
      bump(buckets.manufacturer, tool.manufacturer)
      bump(buckets.component, tool.component_type)
      bump(buckets.geometry, tool.geometry_shape)
      unique(tool.material_groups).forEach(value => bump(buckets.material, value))
      unique(tool.operation_types).forEach(value => bump(buckets.operation, value))
    })
    addOptions(elements.manufacturer, buckets.manufacturer, value => value)
    addOptions(elements.component, buckets.component)
    addOptions(elements.material, buckets.material, value => `${value} · ${MATERIAL_NAMES[value] || value}`)
    addOptions(elements.operation, buckets.operation)
    addOptions(elements.geometry, buckets.geometry, value => value)
  }

  function renderBuildLabel() {
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
      elements.geometry, elements.cutting].filter(element => element.value).length
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
    return `<button class="tool-row${tool.id === state.selectedId ? ' selected' : ''}" type="button" data-tool-id="${escapeHtml(tool.id)}" aria-pressed="${tool.id === state.selectedId}">
      <span class="tool-main"><strong>${escapeHtml(tool.part_number)}</strong><small>${escapeHtml(tool.description)}</small></span>
      <span class="row-maker">${escapeHtml(tool.manufacturer)}</span>
      <span class="row-meta"><span class="badge">${escapeHtml(humanize(tool.component_type))}</span>${groups}${tool.has_cutting_data ? '<span class="badge cutting-data">Cutting data</span>' : ''}</span>
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
    const isIso = geometry.mode === 'iso'
    const dimensions = geometry.dimensions.map(item => ({ label: item.label, value: `${item.value}${item.unit ? ` ${item.unit}` : ''}` }))
    const lines = (isIso ? [
      { label: 'ISO designation', value: geometry.designation },
      { label: 'Shape', value: [geometry.shape_code, geometry.shape_name, geometry.included_angle].filter(Boolean).join(' · ') },
      { label: 'Clearance', value: [geometry.clearance_code, geometry.clearance].filter(Boolean).join(' · ') },
      { label: 'Tolerance code', value: geometry.tolerance_code },
      { label: 'Insert style code', value: geometry.style_code },
      ...dimensions
    ] : [
      { label: 'Manufacturer designation', value: geometry.designation },
      { label: 'Geometry description', value: geometry.summary },
      { label: 'Shape / system', value: geometry.shape_name },
      { label: 'Size', value: geometry.size },
      ...dimensions
    ]).filter(item => item.value)
    const figure = isIso
      ? `<div class="geometry-figure"><svg viewBox="0 0 180 170" role="img" aria-label="Normalized ${escapeHtml(geometry.shape_name || 'insert')} schematic">${geometrySvg(geometry)}</svg></div>`
      : `<div class="geometry-figure"><div class="manufacturer-geometry"><strong>Manufacturer-specific geometry</strong><span>${escapeHtml(geometry.shape_name || geometry.summary || tool.family || tool.part_number)}</span></div></div>`
    return `<div class="geometry-card">
      ${figure}
      <div><div class="geometry-data">${lines.map(item => `<div class="geometry-line"><span>${escapeHtml(item.label)}</span><strong>${escapeHtml(item.value)}</strong></div>`).join('')}</div><p class="geometry-note">${escapeHtml(geometry.note)}${isIso ? ' ISO letter meanings are decoded from the designation.' : ''}</p></div>
    </div>`
  }

  function emptyData(title, message) {
    return `<div class="empty-data"><strong>${escapeHtml(title)}</strong>${escapeHtml(message)}</div>`
  }

  function sourceLocation(item) {
    return [item.source_page_ref, item.source_table_ref].filter(Boolean).join(' · ')
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
    const gradeSelect = grades.length ? `<label>Grade<select data-detail-grade><option value="">All listed grades</option>${grades.map(option => `<option value="${escapeHtml(option.code)}"${state.selectedGrade === option.code ? ' selected' : ''}>${escapeHtml(option.code)}</option>`).join('')}</select></label>` : ''
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
    if (!materials.length) return emptyData('No work-material recommendation available for this selection', 'No recommendation is currently published for this tool and grade selection.')
    return `<div class="material-list">${materials.map(item => `<article class="material-row">
      <span class="material-chip">ISO ${escapeHtml(item.iso_group)}</span>
      <p><strong>${escapeHtml(item.name)}</strong><small>${escapeHtml([item.grade_code, item.material_subgroup || 'Subgroup not specified', humanize(item.suitability)].filter(Boolean).join(' · '))}</small>${item.notes ? `<small>${escapeHtml(item.notes)}</small>` : ''}</p>
    </article>`).join('')}</div>`
  }

  function convertValue(value, unit, target) {
    if (value == null) return { value: null, unit, converted: false }
    if (target === 'source') return { value, unit: sourceUnitLabel(unit), converted: false }
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
    if (!profiles.length) return emptyData('No speeds and feeds available for this selection', 'No cutting recommendation is currently published for this tool, grade, material, and condition selection.')
    return profiles.map(profile => `<article class="cutting-profile" data-profile-id="${escapeHtml(profile.id)}">
      <div class="cutting-head"><strong>ISO ${escapeHtml(profile.iso_material_group)}${profile.material_subgroup ? ` · ${escapeHtml(profile.material_subgroup)}` : ''} · ${escapeHtml(humanize(profile.operation_type))}</strong></div>
      <p class="cutting-context">${escapeHtml([profile.source_material_label, profile.source_grade, profile.source_chipbreaker, humanize(profile.cut_condition)].filter(Boolean).join(' · '))}</p>
      <div class="cutting-values">
        <div><span>Surface speed</span><b>${escapeHtml(rangeMarkup(profile.surface_speed_min, profile.surface_speed_max, profile.surface_speed_unit))}</b>${speedStart(profile) ? `<small>Start: ${escapeHtml(speedStart(profile))}</small>` : ''}</div>
        <div><span>Feed per revolution</span><b>${escapeHtml(rangeMarkup(profile.feed_min, profile.feed_max, profile.feed_unit))}</b></div>
        <div><span>Depth of cut</span><b>${escapeHtml(rangeMarkup(profile.depth_of_cut_min, profile.depth_of_cut_max, profile.depth_of_cut_unit))}</b></div>
      </div>
      <div class="calculator"><label>Stock diameter (${calculatorUnit(profile)})<input type="number" inputmode="decimal" min="0" step="any" data-calc-profile="${escapeHtml(profile.id)}" placeholder="Enter diameter"></label><p class="calculator-output" data-calc-output="${escapeHtml(profile.id)}">Uses the manufacturer start speed; the calculated RPM is not stored as source data.</p></div>
      <p class="audit-line">${escapeHtml(sourceLocation(profile) || 'Source location not recorded')}</p>
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
      const body = `<span><strong>${escapeHtml(title)}</strong><small>${escapeHtml(direction)} · ${escapeHtml(item.notes || 'No notes')}</small></span>`
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
    if (!sources.length) return emptyData('No source linked', 'No manufacturer catalog or website source is currently attached to this record.')
    return `<div class="source-list">${sources.map(source => {
      const link = safeUrl(source.url)
      const location = [source.page_ref, source.document_edition, source.retrieved_at && `retrieved ${source.retrieved_at}`].filter(Boolean).join(' · ')
      return `<article class="source-card">${link ? `<a href="${escapeHtml(link)}" target="_blank" rel="noopener noreferrer">${escapeHtml(source.title)}</a>` : `<strong>${escapeHtml(source.title)}</strong>`}<p>${escapeHtml(humanize(source.source_type))}${location ? ` · ${escapeHtml(location)}` : ''}</p>${source.content_sha256 ? `<p><code>SHA-256 ${escapeHtml(source.content_sha256)}</code></p>` : ''}${source.local_path ? `<p>Local audit file: <code>${escapeHtml(source.local_path)}</code> (not published)</p>` : ''}${source.notes ? `<p>${escapeHtml(source.notes)}</p>` : ''}</article>`
    }).join('')}</div>`
  }

  function factsSection(tool) {
    if (!tool.facts.length) return emptyData('No additional specifications', 'No additional specification rows are attached to this tool.')
    return `<div class="fact-list">${tool.facts.map(fact => `<article class="fact-card"><strong>${escapeHtml(humanize(fact.original_key || fact.key))}</strong><span>${escapeHtml(factValue(fact))}</span></article>`).join('')}</div>`
  }

  function detailSection(title, content, meta = '') {
    return `<section class="detail-section"><div class="section-heading"><h3>${escapeHtml(title)}</h3>${meta ? `<span>${escapeHtml(meta)}</span>` : ''}</div>${content}</section>`
  }

  function renderDetail() {
    const tool = state.toolMap.get(state.selectedId)
    if (!tool) return
    const relationshipCount = [
      ...(state.outgoing.get(tool.id) || []),
      ...(state.incoming.get(tool.id) || [])
    ].filter(item => !item.suppressed).length
    const relationshipLabel = `${relationshipCount} ${relationshipCount === 1 ? 'connection' : 'connections'}`
    const selectors = detailSelectors(tool)
    const materials = filteredMaterials(tool)
    const profiles = filteredProfiles(tool)
    elements.detail.innerHTML = `
      <div class="mobile-detail-bar"><button class="back-button" type="button" data-close-detail>← Results</button></div>
      <header class="detail-header"><div class="detail-kicker"><span>${escapeHtml(humanize(tool.component_type))}</span></div><h2>${escapeHtml(tool.part_number)}</h2><p class="detail-maker">${escapeHtml(tool.manufacturer)}</p><p class="detail-description">${escapeHtml(tool.description)}</p>${selectors}</header>
      ${detailSection('Core specifications', specGrid(tool))}
      ${detailSection('Geometry', geometrySection(tool))}
      ${detailSection('Recommended work materials', materialSection(tool), `${materials.length} recommendations`)}
      ${detailSection('Speeds and feeds', cuttingSection(tool), `${profiles.length} profiles`)}
      ${detailSection('Compatibility path', compatibilitySection(tool), relationshipLabel)}
      ${detailSection('Sources and audit trail', sourceSection(tool), `${sourceIdsFor(tool).length} sources`)}
      ${detailSection('Additional facts', factsSection(tool), `${tool.facts.length} facts`)}
    `
  }

  function clearFilters() {
    elements.search.value = ''
    ;[elements.manufacturer, elements.component, elements.material, elements.operation,
      elements.geometry, elements.cutting].forEach(element => { element.value = '' })
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
      elements.geometry, elements.cutting].forEach(element => element.addEventListener('change', () => applyFilters()))
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
      renderBuildLabel()
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
