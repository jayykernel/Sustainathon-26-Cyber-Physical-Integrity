import { render, screen } from '@testing-library/react'
import '@testing-library/jest-dom/vitest'
import { expect, test } from 'vitest'
import App from './App'

test('renders welcome message', () => {
  render(<App />)
  expect(screen.getByText('Welcome to PhysiGuard')).toBeInTheDocument()
})
