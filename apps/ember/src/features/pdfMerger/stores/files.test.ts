import { createPinia, setActivePinia } from 'pinia'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import * as api from '../api/PdfMergerClient'
import type { FileInfo } from '../api/pdfMergerTypes'
import { useAuthStore } from '../../../stores/auth'
import { useFilesStore } from './files'

vi.mock('../api/PdfMergerClient')

function pdf(id: string, pages = 3): FileInfo {
  return { file_id: id, name: `${id}.pdf`, kind: 'pdf', pages, size: 1000, expires_at: 0 }
}

describe('files store', () => {
  beforeEach(() => setActivePinia(createPinia()))

  it('uploads in drop order and reports failures per file', async () => {
    vi.mocked(api.uploadFile)
      .mockResolvedValueOnce(pdf('f_a'))
      .mockRejectedValueOnce(new Error('Too big.'))
      .mockResolvedValueOnce(pdf('f_c'))
    const files = useFilesStore()

    await files.upload([new File([''], 'a.pdf'), new File([''], 'b.pdf'), new File([''], 'c.pdf')])

    expect(files.sources.map((s) => s.info.file_id)).toEqual(['f_a', 'f_c'])
    expect(files.errors).toEqual(['b.pdf: Too big.'])
    expect(files.uploading).toBe(0)
  })

  it('starts with every page selected', () => {
    const files = useFilesStore()
    files.add(pdf('f_a', 3))

    expect(files.sources[0]).toMatchObject({ range: 'all', pages: [0, 1, 2], rangeError: null, rotate: 0, fit: null })
  })

  it('keeps the last valid pages while a range is invalid', () => {
    const files = useFilesStore()
    files.add(pdf('f_a', 5))

    files.setRange('f_a', '2-3')
    files.setRange('f_a', '9')

    expect(files.sources[0]).toMatchObject({ range: '9', pages: [1, 2], rangeError: 'Pages go from 1 to 5' })
    files.setRange('f_a', '4')
    expect(files.sources[0]).toMatchObject({ pages: [3], rangeError: null })
  })

  it('rotates in 90 degree steps', () => {
    const files = useFilesStore()
    files.add(pdf('f_a'))

    for (let i = 0; i < 4; i++) files.rotate('f_a')

    expect(files.sources[0]!.rotate).toBe(0)
    files.rotate('f_a')
    expect(files.sources[0]!.rotate).toBe(90)
  })

  it('restore adds server files once', async () => {
    vi.mocked(api.listFiles).mockResolvedValue([pdf('f_a'), pdf('f_b')])
    const files = useFilesStore()
    files.add(pdf('f_a'))

    await files.restore()

    expect(files.sources.map((s) => s.info.file_id)).toEqual(['f_a', 'f_b'])
  })

  it('preserves the file and reports a failed delete', async () => {
    vi.mocked(api.deleteFile).mockRejectedValue(new Error('gone'))
    const files = useFilesStore()
    files.add(pdf('f_a'))

    await files.remove('f_a')

    expect(files.sources.map(s => s.info.file_id)).toEqual(['f_a'])
    expect(files.errors[0]).toContain('gone')
  })

  it('moves sources', () => {
    const files = useFilesStore()
    files.add(pdf('f_a'))
    files.add(pdf('f_b'))

    files.moveSource(1, 0)

    expect(files.sources.map((s) => s.info.file_id)).toEqual(['f_b', 'f_a'])
  })
  it('ignores uploads and restores from a previous account', async () => {
    let upload!: (value: FileInfo) => void
    let restore!: (value: FileInfo[]) => void
    vi.mocked(api.uploadFile).mockReturnValueOnce(new Promise(r => { upload = r }))
    vi.mocked(api.listFiles).mockReturnValueOnce(new Promise(r => { restore = r }))
    const auth = useAuthStore()
    const files = useFilesStore()
    const uploading = files.upload([new File(['pdf'], 'a.pdf')])
    const restoring = files.restore()
    auth.account = {id: 2} as NonNullable<typeof auth.account>
    upload(pdf('old')); restore([pdf('old')])
    await Promise.all([uploading, restoring])
    expect(files.sources).toEqual([])
    expect(files.uploading).toBe(0)
  })

})
