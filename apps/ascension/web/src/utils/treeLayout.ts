/** Arrange the prerequisite DAG in columns; retain catalog order within each branch. */
export function layoutTree(nodes: readonly { id: string; requires: string[]; y: number }[]): Map<string, { x: number; y: number }> {
  const byId = new Map(nodes.map(n => [n.id, n]));
  const depths = new Map<string, number>();
  const visiting = new Set<string>();
  const depth = (id: string): number => {
    if (depths.has(id)) return depths.get(id)!;
    if (visiting.has(id)) return 0;
    visiting.add(id);
    const parents = byId.get(id)?.requires.filter(id => byId.has(id)) ?? [];
    const value = parents.length ? 1 + Math.max(...parents.map(depth)) : 0;
    visiting.delete(id);
    depths.set(id, value);
    return value;
  };
  nodes.forEach(n => depth(n.id));
  const positions = new Map<string, { x: number; y: number }>();
  const levels = [...new Set(depths.values())].sort((a, b) => a - b);
  for (const level of levels) {
    const desiredY = (node: typeof nodes[number]): number => {
      const parents = node.requires.map(id => positions.get(id)).filter(p => p !== undefined);
      return parents.length ? parents.reduce((sum, p) => sum + p.y, 0) / parents.length : node.y;
    };
    const column = nodes.filter(n => depths.get(n.id) === level).sort((a, b) => desiredY(a) - desiredY(b) || a.y - b.y);
    let bottom = 24;
    for (const node of column) {
      const y = Math.max(bottom, level === 0 ? bottom : desiredY(node));
      positions.set(node.id, { x: 24 + level * 208, y });
      bottom = y + 112;
    }
  }
  return positions;
}
