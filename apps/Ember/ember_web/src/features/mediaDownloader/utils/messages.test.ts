import { describe, expect, it } from 'vitest'
import { friendlyError } from './messages'

describe('messages', () => {
  it('friendlyError prefers the table, else the server message', () => {
    expect(friendlyError('cancelled', 'x')).toBe('The download was cancelled.')
    expect(friendlyError('connection_lost', 'x')).toContain('connection')
    expect(friendlyError('something_new', 'Server says hi.')).toBe('Server says hi.')
  })
})
