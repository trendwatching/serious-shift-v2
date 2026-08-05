import { MemoryRouter } from '../src/router'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { TopBar } from '../src/shift/chrome'
import { HumanNeeds, PeelTabs, SubShiftList } from '../src/shift/sections'
import { Modules } from '../src/shift/modules'
import { innovationItems, subs } from './fixtures'

describe('accessible modules and navigation', () => {
  it('operates tabs and disclosures with accurate state', async () => {
    const user = userEvent.setup()
    render(<><PeelTabs whatChanging="The change" whyNow="The reason" /><HumanNeeds needs={{ unlocked: 'Agency', threatened: 'Trust' }} /></>)

    const why = screen.getByRole('tab', { name: 'Why now' })
    await user.click(why)
    expect(why).toHaveAttribute('aria-selected', 'true')
    expect(screen.getByRole('tabpanel')).toHaveTextContent('The reason')

    const threatened = screen.getByRole('button', { name: 'Threatened' })
    await user.click(threatened)
    expect(threatened).toHaveAttribute('aria-expanded', 'true')
    expect(document.getElementById(threatened.getAttribute('aria-controls'))).toHaveAttribute('aria-hidden', 'false')
  })

  it('exposes carousel position and accessible next/previous controls', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><SubShiftList subs={subs} hrefFor={(item) => `/map/society/shift/${item.slug}`} /></MemoryRouter>)
    expect(screen.getByRole('status')).toHaveTextContent('1 of 5')
    await user.click(screen.getByRole('button', { name: 'Next sub-shift' }))
    expect(screen.getByRole('status')).toHaveTextContent('2 of 5')
    expect(screen.getByRole('link', { name: /Open sub-shift 2 of 5/ })).toBeInTheDocument()
  })

  it('renders innovations hydrated onto a key shift, tolerating missing fields', () => {
    // The module reaches the page through the registry, not through a prop — the
    // backend injects it into the shift's `modules` list, so this is the real
    // path from a curated link to a rendered card.
    render(
      <MemoryRouter>
        <Modules
          modules={[{ type: 'innovations', data: { items: innovationItems } }]}
          ctx={{ scope: 'key_trend' }}
        />
      </MemoryRouter>,
    )

    expect(screen.getByRole('heading', { name: /Innovations in the wild/i })).toBeInTheDocument()

    // A complete example links out to the article and shows its own origin.
    const link = screen.getByRole('link', { name: /Proof-of-human badge/i })
    expect(link).toHaveAttribute('href', 'https://example.com/acme')
    expect(link).toHaveAttribute('rel', expect.stringContaining('noopener'))
    expect(screen.getByText('Acme')).toBeInTheDocument()
    expect(screen.getByText('food-beverage')).toBeInTheDocument()

    // Same-origin image, which is what the CSP (`img-src 'self'`) permits. An
    // upstream URL here would silently fail to load in a browser.
    const image = document.querySelector('img')
    expect(image.getAttribute('src')).toMatch(/^\/api\/innovations\/\d+\/cover-image/)
    expect(image).toHaveAttribute('alt', '')

    // The minimal example still renders, and is not a link.
    expect(screen.getByText('Bare minimum innovation')).toBeInTheDocument()
    expect(screen.queryByRole('link', { name: /Bare minimum/i })).not.toBeInTheDocument()
    expect(document.querySelectorAll('img')).toHaveLength(1)
  })

  it('drops an innovations module with nothing in it rather than rendering an empty band', () => {
    render(<Modules modules={[{ type: 'innovations', data: { items: [] } }]} ctx={{}} />)
    expect(screen.queryByText(/Innovations in the wild/i)).not.toBeInTheDocument()
  })

  it('uses the exact six-item menu and restores focus when it closes', async () => {
    const user = userEvent.setup()
    render(<MemoryRouter><TopBar /></MemoryRouter>)
    const trigger = screen.getByRole('button', { name: 'Open navigation' })
    await user.click(trigger)
    const dialog = screen.getByRole('dialog', { name: 'Site navigation' })
    expect(within(dialog).getAllByRole('link').map((link) => link.textContent.replace(/^\d+/, '').trim()))
      .toEqual(['Shifts', 'Methodology', 'Subscribe', 'Services', 'TrendWatching', 'About'])
    expect(within(dialog).queryByText('Saved')).not.toBeInTheDocument()
    expect(within(dialog).queryByText('The room')).not.toBeInTheDocument()
    await waitFor(() => expect(within(dialog).getByRole('button', { name: 'Close navigation' })).toHaveFocus())
    fireEvent(dialog, new Event('cancel', { cancelable: true }))
    await waitFor(() => expect(trigger).toHaveFocus())
  })
})
