const STATES = {
  offline: {
    eyebrow: 'Offline',
    title: 'You’re offline.',
    body: 'Reconnect to the internet, then try loading the current map again.',
  },
  timeout: {
    eyebrow: 'Timed out',
    title: 'The map took too long to respond.',
    body: 'The request was stopped after ten seconds. Try again in a moment.',
  },
  server: {
    eyebrow: 'Server error',
    title: 'The map service hit an error.',
    body: 'The last pages you opened remain cached. Try the live service again.',
  },
  unavailable: {
    eyebrow: 'Unavailable',
    title: 'The current map isn’t available.',
    body: 'The service is temporarily unavailable. No empty or stale map has been substituted.',
  },
  request: {
    eyebrow: 'Couldn’t load',
    title: 'The current map couldn’t be loaded.',
    body: 'Check the address or try the request again.',
  },
}

export const failureState = (error) => STATES[error?.kind] || STATES.request
