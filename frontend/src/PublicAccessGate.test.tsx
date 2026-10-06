import { render, screen } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { PublicAccessGate } from './PublicAccessGate'

describe('PublicAccessGate', () => {
  it('clearly limits the public app to the private preview', () => {
    render(<PublicAccessGate />)

    expect(screen.getByRole('heading', { name: /we’re setting the table/i })).toBeInTheDocument()
    expect(screen.getByText(/public allowlist/i)).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /request allowlist access/i })).toHaveAttribute(
      'href',
      expect.stringContaining('hello@useplatter.ca'),
    )
  })
})
