import { useState } from "react";
import { Link } from "react-router-dom";

const steps = [
  { number: "01", title: "Capture the conversation", text: "Record the support session as it happens. No pausing to type, no details left behind." },
  { number: "02", title: "Get a first draft", text: "CaseloadAI finds goals, outcomes, risks, and the participant's own words in the transcript." },
  { number: "03", title: "Review before it goes anywhere", text: "Approve the progress note, edit what you need, and see follow-ups that need a decision." },
];

function Logo() {
  return <Link to="/" className="landing-logo"><span className="landing-mark">c</span><span>caseload<span className="logo-ai">ai</span></span></Link>;
}

function Arrow() {
  return <span aria-hidden="true" className="arrow-icon">↗</span>;
}

export default function Landing() {
  const [menuOpen, setMenuOpen] = useState(false);

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="landing-page" id="top">
      <header className="landing-nav">
        <Logo />
        <button className="mobile-menu-button" onClick={() => setMenuOpen(!menuOpen)} aria-label="Toggle navigation">{menuOpen ? "×" : "☰"}</button>
        <nav className={`landing-links ${menuOpen ? "is-open" : ""}`}>
          <a href="#how-it-works" onClick={closeMenu}>How it works</a>
          <a href="#built-for-care" onClick={closeMenu}>Why CaseloadAI</a>
          <a href="#waitlist" onClick={closeMenu}>Get early access</a>
          <Link to="/notes" className="nav-cta" onClick={closeMenu}>Open workspace <Arrow /></Link>
        </nav>
      </header>

      <main>
        <section className="hero-section">
          <div className="hero-copy">
            <div className="kicker"><span className="live-dot" /> NDIS progress notes, without the late-night catch-up</div>
            <h1>Write less.<br /><em>Notice more.</em></h1>
            <p className="hero-lede">CaseloadAI records a support conversation, drafts the progress note, and flags what needs a closer look. Your team still reviews every word.</p>
            <div className="hero-actions">
              <a href="#waitlist" className="lime-button landing-button">See CaseloadAI in action <Arrow /></a>
              <a href="#how-it-works" className="text-link">See how it works <span>↓</span></a>
            </div>
            <p className="fine-print">Made for the work between the appointments.</p>
          </div>
          <div className="hero-visual" aria-label="CaseloadAI product preview">
            <div className="hero-spark spark-one">✦</div><div className="hero-spark spark-two">+</div>
            <div className="visual-label">From conversation to draft <span>●</span></div>
            <div className="mock-window">
              <div className="mock-topbar"><div className="window-dots"><i /><i /><i /></div><span>NEW PROGRESS NOTE</span><span className="mock-status">● READY</span></div>
              <div className="mock-body">
                <div className="mock-title-row"><div><small>STEP 1 OF 2</small><h2>Record the support conversation</h2></div><span className="ready-pill">Ready when you are</span></div>
                <div className="record-card">
                  <div className="sound-orb"><span className="sound-wave">))))</span></div>
                  <div className="record-copy"><strong>Recording support session</strong><span>Both voices will be transcribed for review.</span></div>
                  <div className="record-time">04:18</div>
                </div>
                <div className="transcript-preview"><div className="transcript-heading"><span>LIVE TRANSCRIPT</span><b>●</b></div><p><mark>Participant</mark> “I’ve been getting more confident taking the bus to work. I still need a bit of help with the route…”</p><div className="transcript-line" /></div>
                <div className="mock-footer"><span>Microphone connected</span><button className="stop-button"><i /> Stop recording</button></div>
              </div>
            </div>
             <div className="float-note"><span className="float-icon">✦</span><div><b>Draft ready for review</b><small>Goal progress found in transcript</small></div><span className="check">✓</span></div>
          </div>
        </section>

        <section className="proof-strip"><p>Designed for the reality of</p><div><span>NDIS providers</span><span>Support workers</span><span>Practice leads</span><span>Participant-centred teams</span></div></section>

         <section className="intro-section" id="built-for-care">
          <div className="section-kicker">The paperwork problem</div>
          <div className="intro-grid"><h2>The session<br />is finished.<br /><em>The note isn’t.</em></h2><div className="intro-text"><p>After a full day of visits, writing the record can become a second shift. Important details get reconstructed from memory, or left for tomorrow.</p><p>CaseloadAI gives your team a usable first draft while the conversation is still fresh. It is an assistant, not an autopilot.</p><a href="#how-it-works" className="dark-link">See the three-step workflow <Arrow /></a></div></div>
        </section>

        <section className="workflow-section" id="how-it-works">
           <div className="workflow-heading"><div className="section-kicker">One conversation at a time</div><h2>A shorter path<br /><em>to a good record.</em></h2></div>
          <div className="steps-grid">{steps.map((step) => <article className="step-card" key={step.number}><span className="step-number">{step.number}</span><div className="step-icon">{step.number === "01" ? "◉" : step.number === "02" ? "⌁" : "✓"}</div><h3>{step.title}</h3><p>{step.text}</p></article>)}</div>
        </section>

        <section className="feature-section"><div className="feature-copy"><div className="section-kicker">The part that needs a person</div><h2>A note can<br />also show<br /><em>what’s next.</em></h2><p>CaseloadAI checks the draft for possible incidents and follow-ups. Those items land in a queue with the context behind them. A person reviews. Nothing is silently sent.</p><a href="#waitlist" className="lime-button landing-button">See the workspace <Arrow /></a></div><div className="task-mock"><div className="task-head"><div><small>REVIEW QUEUE</small><h3>Things to look at <span>today.</span></h3></div><span className="task-count">3</span></div><div className="task-stat-row"><div><b>24h</b><small>shortest response window</small></div><div><b>100%</b><small>human review required</small></div></div><div className="task-list"><div className="task-item"><span className="task-dot orange" /><div><b>Potential incident</b><small>Missed medication mentioned in a note</small></div><span className="task-arrow">↗</span></div><div className="task-item"><span className="task-dot teal" /><div><b>Goal progress</b><small>Travel training milestone recorded</small></div><span className="task-arrow">↗</span></div><div className="task-item muted"><span className="task-dot" /><div><b>Follow-up due</b><small>Check in with participant next Tuesday</small></div><span className="task-arrow">↗</span></div></div></div></section>

        <section className="quote-section"><div className="quote-mark">✦</div><blockquote>AI can write the first draft. A support worker should decide what the record means.</blockquote><div className="quote-byline"><span className="quote-avatar">C</span><span><b>CaseloadAI principle</b><small>Useful automation, with a person in the loop.</small></span></div></section>

        <section className="waitlist-section" id="waitlist"><div className="waitlist-inner"><div className="section-kicker">We’re opening the door</div><h2>Try it on<br /><em>your next shift.</em></h2><p>We’re looking for NDIS teams who want to spend less time reconstructing notes at the end of the day. Tell us how you work and we’ll show you what CaseloadAI can do.</p><a href="mailto:hello@caseloadai.com?subject=CaseloadAI%20early%20access" className="lime-button landing-button">Email the team <Arrow /></a><small>Early access for a small group of providers.</small></div></section>
      </main>

      <footer className="landing-footer"><Logo /><span>© 2026 CaseloadAI</span><div><a href="mailto:hello@caseloadai.com">hello@caseloadai.com</a><a href="#top">Back to top ↑</a></div></footer>
    </div>
  );
}
