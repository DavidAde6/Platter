import { LockKeyhole, Sparkles } from 'lucide-react'

export function PublicAccessGate() {
  return (
    <main className="access-gate">
      <section className="access-gate__card" aria-labelledby="access-gate-title">
        <div className="access-gate__header">
          <div className="access-gate__brand" aria-label="Platter">
            <span className="access-gate__mark" aria-hidden="true"><span /></span>
            <span>Platter</span>
          </div>
          <div className="access-gate__eyebrow">
            <Sparkles aria-hidden="true" />
            <span>Private preview</span>
          </div>
        </div>

        <h1 id="access-gate-title">We’re setting the table.</h1>
        <p className="access-gate__lede">
          Platter is in development and access is currently reserved for our
          public allowlist. We’re making a more thoughtful meal companion—one
          plate at a time.
        </p>

        <div className="access-gate__notice">
          <LockKeyhole aria-hidden="true" />
          <p>
            This preview is not open for general use yet. Joining the
            allowlist does not create an account or grant immediate access.
          </p>
        </div>

        <a className="access-gate__action" href="mailto:hello@useplatter.ca?subject=Platter%20public%20allowlist">
          Request allowlist access
        </a>
        <p className="access-gate__footnote">We’ll be in touch when there’s something real to share.</p>
      </section>
    </main>
  )
}
