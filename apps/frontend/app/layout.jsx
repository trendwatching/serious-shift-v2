import '../src/index.css'

export const metadata = {
  title: 'Serious Shi(f)t — Everything that is about to change',
  description: 'Four domains, eight shifts this week, told as stories.',
}

export const viewport = {
  width: 'device-width',
  initialScale: 1,
  viewportFit: 'cover',   // let the black bar sit under the notch
  themeColor: '#000000',
}

export default function RootLayout({ children }) {
  return (
    <html lang="en">
      <head>
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="" />
        <link
          href="https://fonts.googleapis.com/css2?family=Suez+One&family=Urbanist:wght@400;500;600;700;800&family=Nunito+Sans:opsz,wght@6..12,300;6..12,400;6..12,600;6..12,700;6..12,800&family=JetBrains+Mono:wght@400;500&display=swap"
          rel="stylesheet"
        />
      </head>
      <body>{children}</body>
    </html>
  )
}
