import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { expect, test, vi } from 'vitest'
import App from './App'

test('renders an honest empty console before a run starts', () => {
  vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
  render(<App />)
  expect(screen.getByRole('heading', { name: 'Live console' })).toBeInTheDocument()
  expect(screen.getByText('Waiting for a simulation')).toBeInTheDocument()
  expect(screen.getByRole('contentinfo')).toHaveTextContent('simulated research prototype')
  vi.unstubAllGlobals()
})
