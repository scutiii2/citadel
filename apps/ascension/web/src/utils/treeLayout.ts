import { titleCase } from "./ascension";

export interface TreePoint { x: number; y: number }
interface LayoutNode {
  id: string; requires: string[]; y: number;
  branch?: string | null; kind?: "ability" | "passive"; category?: string;
}
export interface RadialTreeLayout {
  positions: Map<string, TreePoint>;
  center: TreePoint;
  width: number;
  height: number;
  branches: { id: string; label: string }[];
  sharedIds: Set<string>;
}

/** Infer paths from prerequisites, honoring named catalog branches. Coordinates are
 * icon centers; spacing includes names below nodes and the central portrait. */
export function layoutTree(nodes: readonly LayoutNode[]): RadialTreeLayout {
  if (!nodes.length) return { positions: new Map(), center: { x: 200, y: 200 }, width: 400, height: 400, branches: [], sharedIds: new Set() };
  const byId = new Map(nodes.map(n => [n.id, n]));
  const owners = new Map<string, Set<string>>();
  const depths = new Map<string, number>();
  const visiting = new Set<string>();
  function trace(id: string): Set<string> {
    if (owners.has(id)) return owners.get(id)!;
    if (visiting.has(id)) return new Set();
    visiting.add(id);
    const node = byId.get(id)!;
    const parents = node.requires.filter(id => byId.has(id));
    const inherited = new Set(parents.flatMap(id => [...trace(id)]));
    const path = node.branch ? new Set([node.branch]) : parents.length ? inherited : new Set([id]);
    if (!path.size) path.add(id);
    depths.set(id, parents.length ? 1 + Math.max(...parents.map(id => depths.get(id) ?? 0)) : 0);
    owners.set(id, path);
    visiting.delete(id);
    return path;
  }
  nodes.forEach(n => trace(n.id));
  const sharedIds = new Set(nodes.filter(n => owners.get(n.id)!.size > 1 ||
    new Set(n.requires.flatMap(id => [...(owners.get(id) ?? [])])).size > 1).map(n => n.id));
  const branchIds = [...new Set(nodes.flatMap(n => [...owners.get(n.id)!]))];
  const branches = branchIds.map(id => {
    const root = byId.get(id);
    return { id, label: root ? root.kind === "passive" ? "Passive" : titleCase(root.category ?? "Ability") : titleCase(id) };
  });
  const positions = new Map<string, TreePoint>();
  const sector = Math.PI * 2 / Math.max(1, branches.length);
  const start = branches.length === 4 ? -Math.PI * 0.75 : -Math.PI / 2;
  const free = (p: TreePoint): boolean =>
    (Math.abs(p.x) >= 150 || Math.abs(p.y) >= 160) &&
    [...positions.values()].every(q => Math.abs(p.x - q.x) >= 160 || Math.abs(p.y - q.y) >= 132);
  function place(id: string, angle: number, radius: number): number {
    let p = { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
    while (!free(p)) {
      radius += 36;
      p = { x: Math.cos(angle) * radius, y: Math.sin(angle) * radius };
    }
    positions.set(id, p);
    return radius;
  }
  let outerRadius = 220;
  branches.forEach((branch, index) => {
    const members = nodes.filter(n => !sharedIds.has(n.id) && owners.get(n.id)!.has(branch.id));
    const levels = [...new Set(members.map(n => depths.get(n.id)!))].sort((a, b) => a - b);
    let radius = 220;
    for (const level of levels) {
      const layer = members.filter(n => depths.get(n.id) === level).sort((a, b) => a.y - b.y);
      const spread = Math.min(sector * 0.65, 1.2);
      let farthest = radius;
      layer.forEach((node, slot) => {
        const offset = layer.length > 1 ? (slot / (layer.length - 1) - 0.5) * spread : 0;
        farthest = Math.max(farthest, place(node.id, start + sector * index + offset, radius));
      });
      outerRadius = Math.max(outerRadius, farthest);
      radius = farthest + 140;
    }
  });
  const shared = nodes.filter(n => sharedIds.has(n.id)).sort((a, b) => depths.get(a.id)! - depths.get(b.id)!);
  shared.forEach((node, index) => place(node.id, Math.PI / 2 + index * 0.25, Math.max(350, outerRadius * 0.8) + index * 140));
  const all = [{ x: 0, y: 0 }, ...positions.values()];
  const minX = Math.min(...all.map(p => p.x)) - 100;
  const minY = Math.min(...all.map(p => p.y)) - 70;
  const width = Math.max(400, Math.max(...all.map(p => p.x)) - minX + 100);
  const height = Math.max(400, Math.max(...all.map(p => p.y)) - minY + 120);
  positions.forEach(p => { p.x -= minX; p.y -= minY; });
  return { positions, center: { x: -minX, y: -minY }, width, height, branches, sharedIds };
}
