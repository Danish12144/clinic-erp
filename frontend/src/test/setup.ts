// Registers @testing-library/jest-dom's matchers (toBeInTheDocument, etc.)
// onto vitest's `expect` — the /vitest entry point (not the bare package
// root) is what wires up both the runtime matchers and their TS types for
// vitest specifically, rather than assuming a Jest-shaped global.
import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

// @testing-library/react's own auto-cleanup registers against a *global*
// afterEach, which only exists when vitest's `test.globals: true` is set —
// this project deliberately doesn't set that (see vite.config.ts), so
// without this, every render() in a test file leaks into the next test's
// DOM instead of unmounting, confirmed by a real failure (queryByText
// matching leftover markup from a previous test in the same file) the
// first time a file had more than one render() call.
afterEach(() => {
  cleanup()
})
