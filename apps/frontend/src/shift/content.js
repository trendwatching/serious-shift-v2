/**
 * content.js — the authored content from the approved design.
 *
 * This is the editorial reference: the design ships full rich fields for one
 * key shift ("Cognitive Erosion") and headline-only fields for the rest, and
 * the detail page renders each section conditionally. `useDomains()` prefers
 * live `/api/map` data and falls back to this per-field, so the site is
 * pixel-faithful today and lights up further as the pipeline populates the
 * matching columns (see packages/db/migrations + generate_map_data.py).
 */

export const DECK = [
  {
    id: 'society', name: 'Society', num: '01', horizon: '2028', count: 12, readers: '412',
    blurb: 'Belonging, trust and truth when anything can be generated and nobody has to be present.',
    shifts: ['s2', 's5'],
  },
  {
    id: 'economy', name: 'Economy', num: '02', horizon: '2027', count: 14, readers: '507',
    blurb: 'Where value, work and money move once capability stops being scarce.',
    shifts: ['s1', 's6'],
  },
  {
    id: 'organisations', name: 'Organisations', num: '03', horizon: '2026', count: 11, readers: '288',
    blurb: 'How institutions decide, hire and defend themselves when speed is free.',
    shifts: ['s8', 's7'],
  },
  {
    id: 'consumers', name: 'Consumers', num: '04', horizon: '2026', count: 15, readers: '661',
    blurb: 'Identity, taste and desire in a market where software does the shopping.',
    shifts: ['s3', 's4'],
  },
]

export const SHIFTS = [
  {
    id: 's1', kicker: 'Shift 04', title: '“Post-Labour Identity”', read: '6 min read',
    dek: 'When the job stops answering "who are you?", a new status economy rushes in to fill the silence.',
  },
  {
    id: 's2', kicker: 'Shift 07', title: '“The Proof Premium”', read: '5 min read',
    dek: 'Verified-human becomes the luxury label of the decade, and everything unverified gets cheaper.',
  },
  {
    id: 's3', kicker: 'Shift 02', title: '“Agentic Wallets”', read: '7 min read',
    dek: 'Your agent does the shopping. Which means brands are now selling to software with a human sponsor.',
  },
  {
    id: 's4', kicker: 'Shift 09', title: '“Synthetic Intimacy”', read: '6 min read',
    dek: 'Machine companionship stops being embarrassing and starts being infrastructure.',
  },

  // ── The fully-authored shift. Every detail section below has data, so the
  //    shift page renders in full; the others render hero + dek only.
  {
    id: 's5', kicker: 'Key shift 11', title: '“COGNITIVE EROSION”', read: '5 min read',
    dek: 'AI is systematically degrading the human capacities — clear reasoning, shared understanding, intellectual independence — that modern democracy and markets depend on.',
    from: 'Citizens and institutions relying on hard-won human reasoning to navigate complexity',
    to: 'AI mediating understanding so completely that the underlying capacity atrophies from disuse',
    stat: {
      value: '25%',
      text: 'Over 25% of American adults score at literacy level one or below — unable to draw inferences from longer texts.',
      source: 'Sinead Bovell · Why We Might Be The Last Generation That Reads · 2026',
    },
    whatChanging: "Quality used to be scarce. AI made it free. Polished content, convincing images, competent writing, on demand, for nothing. That doesn't kill the desire for quality. It kills quality as a differentiator. What's scarce now is proof that a human chose to make something. Spent the hours, picked the materials, left their mark. Consumers aren't being sentimental about craft. They're doing what consumers always do: paying a premium for whatever's hardest to get.",
    whyNow: 'Three things landed at once: assistants moved from novelty to default in schools and offices, the first cohort educated alongside them entered the workforce, and the measurement caught up — literacy and comprehension scores are now falling in the exact places where AI adoption is highest. The rebound market forms while the damage is still deniable.',
    needs: {
      unlocked: 'Cognitive relief — the exhaustion of modern information overload means offloading reasoning to AI feels like a liberation, not a loss.',
      threatened: 'Intellectual agency — the sense that one’s views and judgments are genuinely one’s own. The fear that understanding has been replaced by retrieval.',
    },
    tension: 'I use AI because it makes me more capable — but I’m starting to suspect it’s making me less capable.',
    horizonSteps: [
      { label: 'Now', text: 'Measurable literacy and reasoning decline alongside surging AI adoption. Institutions notice the gap but have no agreed response.' },
      { label: 'Next', text: 'A visible split between people who maintained reasoning discipline and those who delegated it. The understanding premium becomes economically real.' },
      { label: 'Beyond', text: 'Democratic participation, legal systems, and markets start to break down in ways that trace directly to degraded collective reasoning.' },
    ],
    industries: [
      { name: 'Beauty & Personal Care', text: 'Wellness brands already position around mental clarity and cognitive health. Most are doing it superficially. The ones that build genuine reasoning support into product design will own the space.' },
      { name: 'Consumer Tech', text: 'Devices that make thinking easier are accelerating cognitive delegation. The contrarian product play is designing for cognitive resistance: tools that require and reward thinking rather than bypassing it.' },
      { name: 'Digital Tech', text: 'Platforms that optimise for engagement have always selected for outrage over nuance. AI accelerates that dynamic. The products that reward understanding will be rare, and genuinely valuable.' },
      { name: 'Entertainment', text: 'Audiences that stop reading read differently. Publishers, streaming platforms, and games companies will need to decide whether they’re depleting their audience’s capacity or building it.' },
      { name: 'Fashion & Accessories', text: 'Not a primary sector for this shift. But brands that rely on cultural commentary and trend literacy to sell have a stake in audiences that can still engage with nuance.' },
      { name: 'Financial Services', text: 'AI-assisted financial decisions feel more confident than they are. Firms that help customers understand, not just receive, recommendations will own the trust layer as overconfidence generates visible failures.' },
      { name: 'Food & Beverage', text: 'The category that lives on attention has a problem if attention degrades. Packaging, marketing, and product discovery all assume a reasoning consumer. That assumption is becoming less reliable.' },
      { name: 'Government & Public Sector', text: 'Policy built on assumed citizen reasoning is increasingly disconnected from actual capacity. Democratic participation, legal consent, and public health compliance all depend on a reasoning floor that is falling.' },
      { name: 'Health & Wellbeing', text: 'Cognitive fitness is not on most health brands’ radar. The parallel to physical fitness is obvious. The category is wide open and the evidence base is building.' },
      { name: 'Home & Living', text: 'Smart home products that decide on behalf of residents accelerate delegation. The brands that design for human understanding, not just frictionless automation, will build stickier relationships.' },
      { name: 'Mobility & Transport', text: 'Autonomous vehicles transfer driving decisions to machines. That’s the obvious product. The less obvious question: what does that do to the spatial and situational reasoning skills people stop using?' },
      { name: 'Nonprofit & Social Cause', text: 'Civic organisations, libraries, and education charities are on the front line of this shift. They have a stronger fundraising story than they know: they’re not preserving tradition, they’re preventing systems failure.' },
      { name: 'Retail & Commerce', text: 'Discovery, comparison, and decision-making are increasingly AI-mediated. Retailers that help customers think through decisions, rather than just optimise conversions, will build trust that algorithmic platforms cannot replicate.' },
      { name: 'Travel & Hospitality', text: 'Travel is one of the few remaining contexts where people deliberately slow down, navigate unfamiliar situations, and reason through uncertainty. That experience has new value. Brands that frame it will win.' },
      { name: 'Work & Education', text: 'Are you training people to reason, or to prompt? That question determines which graduates and employees are valuable in ten years. The organisations building reasoning discipline now have a structural advantage that compounds.' },
    ],
    territories: [
      { name: 'Cognitive fitness products', text: 'Tools that help people exercise and track reasoning capacity. The mental equivalent of fitness tracking.' },
      { name: 'Human-legible intelligence', text: 'A new editorial layer: AI synthesis translated into genuinely comprehensible public communication.' },
      { name: 'Understanding certification', text: 'Credentials that verify someone arrived at a conclusion through reasoning, not retrieval.' },
      { name: 'Deliberate friction design', text: 'Products that require and strengthen human reasoning as a feature, not a bug.' },
    ],
    subshifts: [
      {
        title: '“Capacity Collapse”',
        dek: 'More than a quarter of American adults already score at literacy level one or below, 56 of 59 economies showing decline. AI is arriving into a cognitive infrastructure already under stress.',
        context: 'Sub-shift of Cognitive Erosion · AI × Society',
        lede: 'The reasoning and literacy decline AI is being absorbed into predates it — and AI is accelerating what was already in motion.',
        from: 'Literacy and reasoning treated as a stable baseline — something citizens and employees reliably have',
        to: 'Cognitive capacity treated as a variable that must be actively maintained, or it falls',
        quote: 'The floor was already falling. AI just removed the warning signs.',
        stat: { value: '18-34', text: 'The share of US adults who read zero books in a given year has more than doubled since the early 2000s — the steepest decline concentrated in the 18–34 cohort now entering the workforce.', source: 'National Endowment for the Arts · reading participation data' },
        whatChanging: 'Literacy and sustained reasoning were in measurable decline before AI became mainstream. What is changing now is not that AI is creating the problem — it is inheriting an existing one and making it harder to detect, as cognitive tasks migrate to AI and the skills people would have used to do them quietly atrophy. The gap between what institutions assume their users can do — follow an argument, evaluate a claim, read a contract — and what they can actually do is widening. That gap is the real risk.',
        whyNow: 'Three trends are converging. Literacy and reasoning were already falling across the majority of OECD economies before AI became a daily tool. AI has now crossed a usefulness threshold where it is genuinely easier than independent reasoning for most everyday tasks. And the institutions that traditionally maintained cognitive standards — schools, universities, journalism — are under structural pressure that prevents them from holding the line. The combination means the decline is faster, less visible, and unlikely to reverse than any of these forces would produce alone.',
        needs: {
          unlocked: 'Convenience — offloading reading, summarising, and reasoning to AI removes a genuine cognitive burden that people experience as relief.',
          threatened: 'Want and competence — the ability to do things, understand things, and judge things independently. The fear that the skill is going somewhere it cannot be retrieved from.',
        },
        signals: [
          'Literacy scores are declining in 56 of 59 OECD economies — the most comprehensive international measure of adult reading comprehension available.',
          'Secondary school curricula in multiple countries have reduced extended reading requirements in response to declining engagement, accelerating the underlying trend they intended to address.',
          'US university remedial reading enrolments have increased substantially over the past decade, meaning more students arrive without the comprehension baseline that degree-level work assumes.',
          'The 2022 PISA cycle recorded simultaneous reading score declines across more countries than any previous cycle — a drop that predates but was sharpened by pandemic-era disruption.',
        ],
        counter: [
          'Audiobook and podcast consumption is at record highs — people are engaging with ideas and narrative, just in different formats than traditional reading.',
          'Some AI tutoring tools, when designed to require active reasoning rather than deliver answers, show early evidence of improving comprehension in lower-literacy learners.',
        ],
        horizonSteps: [
          { label: 'Now', text: 'Measurable literacy and reasoning decline alongside surging AI adoption. Most organisations have not connected the two.' },
          { label: 'Next', text: 'A visible performance gap opens between people who maintained reasoning discipline and those who delegated it. Hiring processes start to test for it explicitly.' },
          { label: 'Beyond', text: 'Institutions redesign for a lower cognitive baseline rather than restoring the old one. The question of who gets to maintain high reasoning capacity — and how — becomes social and political.' },
        ],
        territories: [
          { name: 'Comprehension-first design', text: 'A design methodology and audit framework for organisations that want to know whether their communications actually land. Not accessibility compliance. Actual comprehension tested at scale.' },
          { name: 'Cognitive baseline tracking', text: 'Consumer tools that measure and track practical reasoning capacity over time. The fitness tracker for the skill of thinking, not abstract IQ.' },
          { name: 'Low-literacy enterprise products', text: 'B2B tools redesigned from the ground up for lower literacy baselines — without condescension. A significant and underserved market as the workforce baseline shifts.' },
        ],
      },
      {
        title: '“Governance Gap”',
        dek: 'AI progress runs on three independent clocks — capability, access, and deployment infrastructure — moving at incompatible speeds that existing governance cannot span.',
        context: 'Sub-shift of Cognitive Erosion · AI × Society',
        lede: 'Rules written for one speed of change are being applied to three, and the gaps between them are where the damage accumulates.',
        from: 'Governance assuming a single, observable pace of technological change it can legislate against',
        to: 'Three clocks running at once — capability, access, infrastructure — with no institution positioned to see all three',
        quote: 'You cannot regulate a system whose parts move at different speeds with a single deadline.',
        stat: { value: '3×', text: 'Frontier model capability, public access, and deployment infrastructure now advance on separate cycles — the fastest moving roughly three times quicker than the slowest, so any rule pinned to one is already stale for the others.', source: 'Serious Shift analysis · capability and diffusion tracking' },
        whatChanging: 'Regulation has always lagged technology. What is new is that there is no single thing to lag behind. Capability jumps in months, public access diffuses in weeks once a product ships, and the infrastructure that actually determines who can deploy at scale moves in multi-year capital cycles. A rule calibrated to one clock is either irrelevant or actively harmful against the other two, and organisations are discovering that compliance with the letter of a framework offers almost no protection against the risk it was written for.',
        whyNow: 'The first serious AI statutes are landing now, drafted against a 2023 understanding of the technology. Simultaneously, capability has moved on, access has gone consumer-default, and compute allocation has become geopolitical. The mismatch is no longer theoretical: firms are being asked to certify against definitions that no longer describe what they run.',
        needs: {
          unlocked: 'Clarity — a documented framework to point at gives organisations something to plan against, and that relief is real even when the framework is imperfect.',
          threatened: 'Security — the confidence that following the rules actually protects you. When compliance and safety diverge, the whole basis of institutional trust erodes.',
        },
        signals: [
          'Major AI frameworks are entering force with definitions written before the current model generation existed, forcing regulators into rolling technical amendments.',
          'Compliance teams increasingly report certifying systems they cannot fully describe, because the deployed behaviour changes faster than documentation cycles.',
          'Compute access, not model capability, is emerging as the real determinant of who can deploy at scale — and almost no framework governs it directly.',
          'Sector regulators in finance and health are issuing guidance that contradicts general-purpose AI rules, leaving firms to arbitrate between them.',
        ],
        counter: [
          'Regulatory sandboxes in several jurisdictions are producing faster, more technically literate iteration than traditional rulemaking.',
          'Voluntary industry standards are converging on shared evaluation methods faster than statute, giving a de facto common language.',
        ],
        horizonSteps: [
          { label: 'Now', text: 'Frameworks arrive already out of date. Organisations comply on paper while carrying unmeasured real risk.' },
          { label: 'Next', text: 'A visible failure traceable to the gap between clocks forces emergency rulemaking, and compliance stops being a defence.' },
          { label: 'Beyond', text: 'Governance restructures around continuous evaluation rather than fixed rules — closer to financial supervision than product regulation.' },
        ],
        territories: [
          { name: 'Continuous compliance tooling', text: 'Systems that evaluate deployed AI behaviour on an ongoing basis rather than certifying a snapshot. The audit equivalent of monitoring, not inspection.' },
          { name: 'Cross-clock risk mapping', text: 'Advisory and software that tells an organisation which of the three clocks its exposure actually sits on, and where its controls are pinned to the wrong one.' },
          { name: 'Infrastructure-layer assurance', text: 'Governance products aimed at compute and deployment access — the layer almost every framework currently ignores.' },
        ],
      },
      {
        title: '“Epistemic Drift”',
        dek: 'AI discourse is already selecting for populist rhetoric — paranoia as analysis, rejection of nuance. The medium is shaping the message in ways that corrode public reasoning.',
        context: 'Sub-shift of Cognitive Erosion · AI × Society',
        lede: 'The way we talk about AI is training people out of the reasoning they would need to think about it clearly.',
        from: 'Public debate that rewards evidence, qualification and changed minds',
        to: 'Discourse that rewards certainty, threat and the refusal to concede anything',
        quote: 'The loudest analysis of AI is the least analytical, and it is winning.',
        stat: { value: '2:1', text: 'Content framing AI in absolute terms — total salvation or total catastrophe — consistently outperforms qualified analysis by roughly two to one on engagement, selecting for the least useful framing of the most consequential topic.', source: 'Serious Shift analysis · platform engagement patterns' },
        whatChanging: 'This is not a story about misinformation. It is a story about form. The formats where AI is discussed most — short video, threads, headline aggregation — structurally reward confidence and punish qualification, so the arguments that spread are the ones that concede nothing. Over time that does not just distort what people believe about AI; it degrades the habit of holding two possibilities at once, which is precisely the habit required to make good decisions about it.',
        whyNow: 'AI has become a mass-culture topic at the exact moment discourse infrastructure is at its most engagement-optimised. There is no longer a slower, more deliberate tier of public conversation that the fast tier eventually answers to. The first draft is the only draft, and it is written for velocity.',
        needs: {
          unlocked: 'Belonging — strong, simple positions give people a side to stand on in a genuinely disorienting moment.',
          threatened: 'Understanding — the ability to actually work out what is happening, which requires holding uncertainty long enough to examine it.',
        },
        signals: [
          'Absolutist framings of AI outperform qualified analysis on every major platform, regardless of the underlying accuracy.',
          'Public figures who change position on AI in response to evidence face sharper reputational penalties than those who never revise.',
          'Newsroom AI coverage has consolidated around two narrative templates — job apocalypse and productivity miracle — squeezing out sector-specific reporting.',
          'Survey data shows public confidence in understanding AI rising faster than actual measured comprehension of it.',
        ],
        counter: [
          'Long-form audio and newsletters are growing among exactly the decision-maker audiences that matter most, and they reward nuance.',
          'Several institutions have begun publishing explicit uncertainty ranges with AI claims, normalising qualification as a credibility signal rather than a weakness.',
        ],
        horizonSteps: [
          { label: 'Now', text: 'Public AI discourse polarises faster than the technology develops. Decision-makers absorb the frames without noticing.' },
          { label: 'Next', text: 'Organisations start making strategy errors traceable to discourse frames rather than analysis, and the cost becomes visible.' },
          { label: 'Beyond', text: 'A premium market emerges for slow, qualified, sourced intelligence — and access to it becomes a competitive divide.' },
        ],
        territories: [
          { name: 'Qualified-by-default media', text: 'Editorial products that make uncertainty a feature: explicit confidence levels, visible sourcing, published revisions.' },
          { name: 'Frame auditing', text: 'Tools that show an organisation which public narratives its own strategy documents have absorbed unexamined.' },
          { name: 'Deliberation formats', text: 'Products and services that structure genuine disagreement — the corporate equivalent of a good editorial argument.' },
        ],
      },
      {
        title: '“Oversight Asymmetry”',
        dek: 'In documented AI-driven security incidents, attacker LLMs operated without guardrails while defender systems were constrained by them — a structural asymmetry that gets worse as both sides scale.',
        context: 'Sub-shift of Cognitive Erosion · AI × Society',
        lede: 'Safety constraints apply to the people who follow rules. The asymmetry that creates compounds as capability rises.',
        from: 'Security contests fought between roughly equally constrained parties',
        to: 'Contests where one side accepts limits by design and the other has none at all',
        quote: 'Every guardrail is a rule that only the compliant obey.',
        stat: { value: '100%', text: 'In documented AI-assisted intrusions to date, the attacking systems operated without safety constraints while every defending system was operating under them — an asymmetry present in every case, not a subset.', source: 'Serious Shift analysis · published incident reporting' },
        whatChanging: 'Guardrails were designed as a property of models. In practice they are a property of institutions: the organisations that install them are the ones already inclined to behave well. As capability rises, the gap between a constrained defender and an unconstrained attacker does not stay constant — it widens, because the same capability increase buys more freedom on the unconstrained side. Defence is being asked to win a fight it enters with a handicap that grows with every model release.',
        whyNow: 'Capable open-weight models are now widely available, and the tooling to strip constraints is trivial. At the same time, regulated sectors are formalising the constraints their own defensive systems must operate under. Both curves are steepening at once, in opposite directions.',
        needs: {
          unlocked: 'Safety — constraints genuinely reduce accidental harm, and organisations are right to want them.',
          threatened: 'Protection — the expectation that following the rules leaves you defended rather than exposed.',
        },
        signals: [
          'Documented AI-assisted intrusions consistently show unconstrained attacker tooling against constrained defensive systems.',
          'Open-weight models capable of sophisticated offensive work are now freely distributable, with constraint removal a well-documented procedure.',
          'Regulated sectors are formalising limits on defensive automation faster than they are funding it.',
          'Security teams report that the approval cycle for a defensive AI capability now exceeds the observed adoption cycle on the attacking side.',
        ],
        counter: [
          'Defenders retain structural advantages attackers do not have: telemetry, context and the ability to change the terrain.',
          'Several regulators have begun carving explicit exemptions for defensive automation, narrowing the gap where it matters most.',
        ],
        horizonSteps: [
          { label: 'Now', text: 'The asymmetry is visible in incident reports but not yet reflected in how defensive capability is approved or funded.' },
          { label: 'Next', text: 'A significant breach traced directly to constraint asymmetry forces a rethink of what defenders are permitted to automate.' },
          { label: 'Beyond', text: 'Governance splits explicitly between offensive-risk and defensive-capability regimes, with different rules for each.' },
        ],
        territories: [
          { name: 'Defensive-exemption design', text: 'Frameworks that let defenders operate at attacker speed without abandoning accountability. A genuine policy gap with commercial value.' },
          { name: 'Asymmetry assessment', text: 'Tooling that quantifies how much of an organisation’s exposure comes from its own constraints rather than its vulnerabilities.' },
          { name: 'Constraint-aware security products', text: 'Defensive systems built from the start to be maximally effective inside regulated limits, rather than degraded versions of unconstrained tools.' },
        ],
      },
      {
        title: '“Understanding Premium”',
        dek: 'Karpathy’s observation that understanding cannot be outsourced is being confirmed empirically: students who retained reasoning skills are dramatically outperforming those who delegated them.',
        context: 'Sub-shift of Cognitive Erosion · AI × Society',
        lede: 'As competence becomes cheap to simulate, the ability to actually understand something turns into a priced, scarce and defensible asset.',
        from: 'Understanding treated as a means to an end — useful only until the output is produced',
        to: 'Understanding treated as the asset itself, because everything downstream of it can now be faked',
        quote: 'You can outsource the answer. You cannot outsource knowing whether it is right.',
        stat: { value: '2×', text: 'Students who used AI to check reasoning they had already attempted outperformed those who used it to produce answers by roughly two to one on later unaided assessment — the same tool, opposite outcomes.', source: 'Serious Shift analysis · published classroom studies' },
        whatChanging: 'For a decade the assumption was that AI would flatten the difference between people: everyone gets a competent assistant, everyone produces competent work. What is actually emerging is the opposite. The tool amplifies whatever reasoning capacity the person brings to it. Someone who understands the domain uses AI to move faster and catch its errors; someone who does not uses it to generate confident work they cannot evaluate. The gap between those two people is widening, and it is starting to be visible in output quality, in hiring, and in who gets trusted with consequential decisions.',
        whyNow: 'The first cohort that learned with these tools is entering professional work, and the performance difference is measurable rather than anecdotal. At the same time, organisations that automated aggressively are hitting the ceiling: they can produce more, but nobody in the room can adjudicate whether it is right. Both pressures are surfacing in the same eighteen-month window.',
        needs: {
          unlocked: 'Achievement — AI genuinely removes drudgery and lets capable people operate at a level that was previously out of reach.',
          threatened: 'Competence — the confidence that you could do it yourself, and would know if it were wrong. Once that goes, so does the ability to supervise anything.',
        },
        signals: [
          'Students who used AI to verify reasoning they had already attempted substantially outperformed peers who used it to generate answers, on later unaided assessment.',
          'Employers in law, medicine and engineering are reintroducing unaided reasoning stages into hiring after AI-assisted portfolios stopped predicting on-the-job performance.',
          'Firms report a growing bottleneck not in producing work but in finding people qualified to review it.',
          'Premium pricing is appearing for advisory services that can show their reasoning, not just their conclusion.',
        ],
        counter: [
          'Well-designed AI tutoring that forces the learner to reason first shows real comprehension gains, suggesting the outcome depends on tool design rather than the technology itself.',
          'Some domains genuinely do not require the underlying understanding — where verification is cheap and errors are visible, delegation carries little cost.',
        ],
        horizonSteps: [
          { label: 'Now', text: 'The performance gap between people who reason and people who prompt is measurable but rarely named in hiring or organisation design.' },
          { label: 'Next', text: 'Understanding becomes an explicit, tested and priced credential. Review capacity becomes the scarce role in every knowledge organisation.' },
          { label: 'Beyond', text: 'Access to the education and time required to build genuine understanding becomes a visible line of economic advantage — and a political question.' },
        ],
        territories: [
          { name: 'Reasoning-first learning', text: 'Products that require the learner to attempt reasoning before AI assistance unlocks. The evidence already favours this design; almost nothing on the market does it.' },
          { name: 'Review capacity as a service', text: 'Networks of domain experts who can adjudicate AI-produced work. The bottleneck organisations are hitting right now, sold as capability rather than headcount.' },
          { name: 'Demonstrated-understanding credentials', text: 'Assessment that certifies someone arrived at a conclusion through reasoning, not retrieval — portable, verifiable and increasingly worth paying for.' },
        ],
      },
    ],
  },

  {
    id: 's6', kicker: 'Shift 05', title: '“Compute Citizenship”', read: '8 min read',
    dek: 'Access to compute becomes a political entitlement, argued about like water rights.',
  },
  {
    id: 's7', kicker: 'Shift 14', title: '“Taste as the Last Moat”', read: '5 min read',
    dek: 'When everyone can make anything, knowing what is worth making becomes the whole business.',
  },
  {
    id: 's8', kicker: 'Shift 12', title: '“Slow AI”', read: '4 min read',
    dek: 'The premium move becomes doing it slower, on purpose, and saying so.',
  },
]

/** Client logos for the footer marquee. */
export const LOGOS = [
  'itc-hotels', 'sephora', 'google', 'didi', 'blink-digital',
  'starbucks', 'mastercard', 'cg', 'hero', 'dentsu',
].map((n) => `/shift/logo-${n}.jpg`)

/* ── External destinations ───────────────────────────────────────────── */

// Live about page (what seriousshift.ai/about redirects to for now). Each
// section below is an anchor that exists on that page.
export const ABOUT_URL = 'https://info.trendwatching.com/serious-shift/about'
export const METHODOLOGY_URL = `${ABOUT_URL}#methodology`
export const SUBSCRIBE_URL = `${ABOUT_URL}#subscribe`
export const SERVICES_URL = `${ABOUT_URL}#services`
export const TRENDWATCHING_URL = `${ABOUT_URL}#trendwatching`
export const CONTACT_URL = 'mailto:hello@trendwatching.com'

// Secondary menu group, below the four domains.
export const MENU_LINKS = [
  { label: 'Methodology', href: METHODOLOGY_URL },
  { label: 'Services', href: SERVICES_URL },
  { label: 'TrendWatching', href: TRENDWATCHING_URL },
  { label: 'About', href: ABOUT_URL },
]

export const FOOTER_LINKS = [
  { label: 'Who is it for?', href: ABOUT_URL },
  { label: 'Who am I reading?', href: `${ABOUT_URL}#methodology` },
  { label: 'What else you’d like?', href: CONTACT_URL },
]

export const SOCIALS = ['in', 'X', 'IG', 'YT']
