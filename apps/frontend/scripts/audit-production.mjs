import { spawnSync } from 'node:child_process'
import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'

const severity = { info: 0, low: 1, moderate: 2, high: 3, critical: 4 }
const waiverPath = fileURLToPath(new URL('../../../security/audit-waivers.json', import.meta.url))
const waivers = JSON.parse(readFileSync(waiverPath, 'utf8')).npm || []
const today = new Date().toISOString().slice(0, 10)

for (const waiver of waivers) {
  for (const field of ['id', 'reason', 'owner', 'expires']) {
    if (!waiver[field]) throw new Error(`npm audit waiver is missing ${field}`)
  }
  if (waiver.expires < today) throw new Error(`${waiver.id} waiver expired on ${waiver.expires}`)
}

const result = spawnSync('npm', ['audit', '--omit=dev', '--audit-level=high', '--json'], {
  cwd: fileURLToPath(new URL('..', import.meta.url)),
  encoding: 'utf8',
})
if (!result.stdout) {
  process.stderr.write(result.stderr || 'npm audit returned no report\n')
  process.exit(result.status || 1)
}

const report = JSON.parse(result.stdout)
const vulnerabilities = report.vulnerabilities || {}
const waived = new Set()

function advisoryId(item) {
  return item.url?.split('/').pop() || String(item.source || item.name)
}

function unresolved(name, seen = new Set()) {
  if (seen.has(name)) return []
  seen.add(name)
  const vulnerability = vulnerabilities[name]
  if (!vulnerability || severity[vulnerability.severity] < severity.high) return []

  const findings = []
  for (const item of vulnerability.via || []) {
    if (typeof item === 'string') {
      findings.push(...unresolved(item, new Set(seen)))
      continue
    }
    if (severity[item.severity] < severity.high) continue
    const id = advisoryId(item)
    const waiver = waivers.find((candidate) => candidate.id === id)
    if (waiver) waived.add(id)
    else findings.push(`${id}: ${item.title}`)
  }
  if (!(vulnerability.via || []).length) findings.push(`${name}: unresolved ${vulnerability.severity} vulnerability`)
  return findings
}

const findings = [...new Set(Object.keys(vulnerabilities).flatMap((name) => unresolved(name)))]
for (const id of waived) console.warn(`WAIVED ${id} until ${waivers.find((item) => item.id === id).expires}`)
if (findings.length) {
  console.error(`Blocking npm audit findings:\n${findings.map((item) => `- ${item}`).join('\n')}`)
  process.exit(1)
}
console.log('npm production audit passed (high/critical findings blocked; active waivers validated)')
