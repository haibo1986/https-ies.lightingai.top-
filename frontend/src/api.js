const API_BASE = import.meta.env.VITE_API_BASE_URL || ''

async function parseResponse(response) {
  const data = await response.json().catch(() => ({}))
  if (!response.ok) throw new Error(data.error || `请求失败（${response.status}）`)
  return data
}

export async function uploadIes(file) {
  const form = new FormData()
  form.append('file', file)
  return parseResponse(await fetch(`${API_BASE}/api/upload`, { method: 'POST', body: form }))
}

export async function uploadSourceReport(file) {
  const form = new FormData()
  form.append('file', file)
  return parseResponse(await fetch(`${API_BASE}/api/source-report`, { method: 'POST', body: form }))
}

export async function generateIes(payload) {
  return parseResponse(await fetch(`${API_BASE}/api/generate`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(payload),
  }))
}

export const downloadUrl = (path) => path ? `${API_BASE}${path}` : ''

export async function fetchLedLibrary() {
  return parseResponse(await fetch(`${API_BASE}/api/led-library`))
}

export async function saveLedModel(model) {
  return parseResponse(await fetch(`${API_BASE}/api/led-library`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(model),
  }))
}
