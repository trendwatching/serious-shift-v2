import '../src/index.css'

export const metadata = {
  title: 'Serious Shi(f)t — AGI Consumer Intelligence',
}

export const viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({ children }) {
  return (
    // Light is the default theme (the new bright "Serious Shi(f)t" look).
    // useTheme toggles the `light` class off → dark. Rendering `light` here
    // avoids a first-paint flash of the dark palette.
    <html lang="en" className="light">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Poppins:wght@400;500;600;700;800&family=Inter:wght@300;400;500;600&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body className="bg-paper text-ink">{children}</body>
    </html>
  )
}
