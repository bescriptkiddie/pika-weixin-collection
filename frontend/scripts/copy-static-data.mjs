import fs from 'fs'
import path from 'path'
import { fileURLToPath } from 'url'

const __filename = fileURLToPath(import.meta.url)
const __dirname = path.dirname(__filename)
const frontendRoot = path.resolve(__dirname, '..')
const projectRoot = path.resolve(frontendRoot, '..')
const distDataDir = path.join(frontendRoot, 'dist', 'data')
const dataRoot = path.join(projectRoot, 'data')

const filesToCopy = [
  'message_info.json',
  'name2fakeid.json',
  'message_detail_text.json',
  'operation_logs.jsonl',
]

fs.mkdirSync(distDataDir, { recursive: true })

for (const filename of filesToCopy) {
  const src = path.join(dataRoot, filename)
  const dest = path.join(distDataDir, filename)
  if (fs.existsSync(src)) {
    fs.copyFileSync(src, dest)
  }
}

const coversSrc = path.join(dataRoot, 'covers')
const coversDest = path.join(distDataDir, 'covers')
if (fs.existsSync(coversSrc)) {
  fs.rmSync(coversDest, { recursive: true, force: true })
  fs.cpSync(coversSrc, coversDest, { recursive: true })
}
