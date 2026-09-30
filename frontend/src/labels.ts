/** Display name for an anchor source. Internal ids (role:<name>, generic, mechanical, reference) stay as stored. */
export function sourceLabel(id: string): string {
  if (id.startsWith('role:')) return `Stakeholder: ${id.slice(5)}`
  if (id === 'generic') return 'Generic'
  if (id === 'mechanical') return 'Mechanical'
  if (id === 'reference') return "Analyst's original"
  return id
}
