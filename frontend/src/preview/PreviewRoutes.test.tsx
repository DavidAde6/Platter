import { cleanup, fireEvent, render, screen, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it } from 'vitest'
import { Navigate, RouterProvider, createMemoryRouter } from 'react-router-dom'
import { PreviewLayout } from './PreviewLayout'
import {
  PreviewDiscoverPage,
  PreviewPreferencesPage,
  PreviewRecommendationPage,
  PreviewRememberPage,
  PreviewScanPage,
  PreviewSwapsPage,
} from './PreviewPages'

const routes = [
  {
    path: '/preview',
    element: <PreviewLayout />,
    children: [
      { index: true, element: <Navigate to="scan" replace /> },
      { path: 'scan', element: <PreviewScanPage /> },
      { path: 'preferences', element: <PreviewPreferencesPage /> },
      { path: 'discover', element: <PreviewDiscoverPage /> },
      { path: 'recommendation', element: <PreviewRecommendationPage /> },
      { path: 'swaps', element: <PreviewSwapsPage /> },
      { path: 'remember', element: <PreviewRememberPage /> },
    ],
  },
]

function renderPreview(path: string) {
  const router = createMemoryRouter(routes, { initialEntries: [path] })
  return render(<RouterProvider router={router} />)
}

afterEach(cleanup)

describe('public preview routes', () => {
  it('redirects /preview to the scan mockup', async () => {
    renderPreview('/preview')
    expect(await screen.findByRole('heading', { name: /here.*what we found/i })).toBeInTheDocument()
  })

  it.each([
    ['/preview/scan', /here.*what we found/i],
    ['/preview/preferences', /what sounds good right now/i],
    ['/preview/discover', /what are you in the mood for/i],
    ['/preview/recommendation', /miso mushroom noodles/i],
    ['/preview/swaps', /change one thing/i],
    ['/preview/remember', /bring back a meal you loved/i],
  ])('renders %s without launch dates', (path, heading) => {
    renderPreview(path)
    expect(screen.getByRole('heading', { name: heading })).toBeInTheDocument()
    expect(screen.queryByText(/October 1|April 2027|January 1, 2027/i)).not.toBeInTheDocument()
  })

  it('moves from the scan screen into preferences', async () => {
    renderPreview('/preview/scan')
    fireEvent.click(screen.getByRole('link', { name: /record meal/i }))
    await waitFor(() => expect(screen.getByRole('heading', { name: /what sounds good right now/i })).toBeInTheDocument())
  })
})
