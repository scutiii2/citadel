// Builds the NSIS installer, then copies it to <Citadel>/releases.
import { spawnSync } from 'node:child_process'
import { cpSync, mkdirSync, readdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const root = resolve(dirname(fileURLToPath(import.meta.url)), '..')
const out = resolve(root, '..', '..', 'releases')
const build = spawnSync('pnpm', ['tauri', 'build'], { cwd: root, stdio: 'inherit', shell: true })
if (build.status !== 0) process.exit(build.status ?? 1)

const nsis = join(root, 'src-tauri', 'target', 'release', 'bundle', 'nsis')
const files = readdirSync(nsis).filter((f) => f.endsWith('.exe'))
if (!files.length) throw new Error(`No installer found in ${nsis}`)
mkdirSync(out, { recursive: true })
for (const f of files) {
  cpSync(join(nsis, f), join(out, f))
  console.log(`Release: ${join(out, f)}`)
}
