import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { MemoryRouter } from '../src/lib/router'
import { Header } from '../src/chrome/Header'
import { HumanNeeds, PeelTabs } from '../src/modules/interactive'
import { WorkWithUs } from '../src/chrome/WorkWithUs'
import { Modules } from '../src/modules'
import { innovationItems } from './fixtures'

const ctx = { scope: 'shift', domain: { id: 'society', grad: 'none' } }

describe('modules', () => {
  it('switches peel tabs and keeps both panels mounted', async () => {
    const user = userEvent.setup()
    render(<PeelTabs data={{ whats_changing: 'The change', why_now: 'The reason' }} ctx={ctx} />)

    // Both panels stay in the DOM: the stack is pinned to the taller of them,
    // so switching must not resize the page under the reader.
    expect(screen.getAllByRole('tabpanel')).toHaveLength(2)

    const why = screen.getByRole('tab', { name: 'Why now' })
    await user.click(why)
    expect(why).toHaveAttribute('aria-selected', 'true')
  })

  it('expands one human need at a time', async () => {
    const user = userEvent.setup()
    render(<HumanNeeds data={{ unlocked: 'Agency', threatened: 'Trust' }} ctx={ctx} />)
    const threatened = screen.getByRole('button', { name: /Threatened/ })
    await user.click(threatened)
    expect(threatened).toHaveAttribute('aria-expanded', 'true')
    expect(screen.getByRole('button', { name: /Unlocked/ })).toHaveAttribute('aria-expanded', 'false')
  })

  it('renders innovations hydrated onto a shift, tolerating missing fields', () => {
    render(
      <MemoryRouter>
        <Modules modules={[{ type: 'innovations', data: { items: innovationItems } }]} ctx={ctx} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('heading', { name: /Innovations in the wild/i })).toBeInTheDocument()

    const link = screen.getByRole('link', { name: /Proof-of-human badge/i })
    expect(link).toHaveAttribute('href', 'https://example.com/acme')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(screen.getByText('Acme')).toBeInTheDocument()

    // The minimal example still renders, and is not a link.
    expect(screen.getByText('Bare minimum innovation')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Bare minimum/i })).not.toBeInTheDocument()
  })

  it('leaves the territories rail to its own cards', () => {
    // The Work With Us CTA used to be the last cell here, which is why it only
    // ever reached Consumers — the three other spheres hide this module.
    render(
      <MemoryRouter>
        <Modules modules={[{ type: 'territories', data: { items: [{ name: 'Proof rails', text: 'Sell the receipt.' }] } }]} ctx={ctx} />
      </MemoryRouter>,
    )
    expect(screen.getByText('Proof rails')).toBeInTheDocument()
    expect(screen.queryByText(/Ready for the shift/i)).not.toBeInTheDocument()
  })

  it('drops an empty module rather than rendering an empty band', () => {
    render(<Modules modules={[{ type: 'innovations', data: { items: [] } }]} ctx={ctx} />)
    expect(screen.queryByText(/Innovations in the wild/i)).not.toBeInTheDocument()
  })

  it('surfaces an unknown type instead of silently dropping it', () => {
    render(<Modules modules={[{ type: 'not_a_module', data: {} }]} ctx={ctx} />)
    expect(screen.getByRole('status')).toHaveTextContent(/temporarily unavailable/i)
  })
})

describe('header navigation', () => {
  it('opens the five-item dropdown and restores focus when it closes', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><Header /></MemoryRouter>)
    const trigger = screen.getByRole('button', { name: 'Open navigation' })
    await user.click(trigger)

    const dialog = screen.getByRole('dialog', { name: 'Site navigation' })
    // No Shifts row: it pointed at `/`, which the logo already covers and the
    // router's same-route guard made a visible no-op (13 Aug 2026 review).
    // Its live-count meta slot went with it — the 5 Aug Miro review had
    // already removed the descriptor column from every other row.
    expect(within(dialog).getAllByRole('link').map((l) => l.querySelector('span').textContent))
      .toEqual(['Methodology', 'Subscribe', 'Services', 'TrendWatching', 'About'])
    expect(within(dialog).queryByText('Every domain')).toBeNull()

    fireEvent.keyDown(document, { key: 'Escape' })
    await waitFor(() => expect(trigger).toHaveFocus())
  })
})

describe('work with us', () => {
  it('is a band of its own, pointing at the About page services section', () => {
    render(<MemoryRouter><WorkWithUs /></MemoryRouter>)
    expect(screen.getByRole('heading', { name: /Ready for the shift/i })).toBeInTheDocument()
    expect(screen.getByRole('link', { name: /Talk To Us/i })).toHaveAttribute('href', '/about#services')
  })
})
