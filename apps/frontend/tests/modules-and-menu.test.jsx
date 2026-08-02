import { MemoryRouter } from 'react-router-dom'
import { fireEvent, render, screen, waitFor, within } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it } from 'vitest'
import { TopBar } from '../src/shift/chrome'
import { HumanNeeds, PeelTabs, SubShiftList } from '../src/shift/sections'
import { subs } from './fixtures'

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
    render(<SubShiftList subs={subs} onOpen={() => {}} />)
    expect(screen.getByRole('status')).toHaveTextContent('1 of 5')
    await user.click(screen.getByRole('button', { name: 'Next sub-shift' }))
    expect(screen.getByRole('status')).toHaveTextContent('2 of 5')
    expect(screen.getByRole('button', { name: /Open sub-shift 2 of 5/ })).toBeInTheDocument()
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
