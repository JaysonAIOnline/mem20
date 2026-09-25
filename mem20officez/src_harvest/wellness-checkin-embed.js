/**
 * Wellness Check-In Widget for mem20
 * Embeddable component — drop into any page.
 *
 * Usage:
 *   <div id="wellness-checkin"></div>
 *   <script src="wellness-checkin-embed.js"></script>
 *   <script>initWellnessCheckin('wellness-checkin');</script>
 *
 * Or auto-init with data attribute:
 *   <div data-wellness-checkin></div>
 *   <script src="wellness-checkin-embed.js" async></script>
 */
(function() {
  'use strict';

  // Scoped CSS — uses unique prefix to avoid host page conflicts
  const STYLE_ID = 'wc-embed-styles';
  const CSS = `
    #WC_SCOPE div, #WC_SCOPE span, #WC_SCOPE button, #WC_SCOPE textarea,
    #WC_SCOPE h1, #WC_SCOPE h4, #WC_SCOPE p, #WC_SCOPE ul, #WC_SCOPE li {
      margin: 0; padding: 0; box-sizing: border-box;
    }
    #WC_SCOPE {
      --wc-bg: #0a0a1a;
      --wc-surface: #111128;
      --wc-surface-hover: #1a1a3a;
      --wc-border: #00ff88;
      --wc-border-dim: #004422;
      --wc-text: #e0e0e0;
      --wc-text-muted: #00aa55;
      --wc-accent: #00ff88;
      --wc-accent-glow: rgba(0, 255, 136, 0.15);
      --wc-warning: #ffcc00;
      --wc-danger: #ff4444;
      --wc-radius: 4px;
      --wc-transition: 0.2s cubic-bezier(0.4, 0, 0.2, 1);

      font-family: 'Courier New', Courier, monospace;
      color: var(--wc-text);
      line-height: 1.6;
      width: 100%;
      max-width: 600px;
      background: var(--wc-surface);
      border: 1px solid var(--wc-border);
      border-radius: var(--wc-radius);
      overflow: hidden;
      box-shadow: 0 0 40px rgba(0, 255, 136, 0.08);
    }
    #WC_SCOPE .wc-header {
      padding: 28px 28px 20px;
      border-bottom: 1px solid var(--wc-border-dim);
      text-align: center;
    }
    #WC_SCOPE .wc-header .wc-icon {
      font-size: 1.8rem;
      margin-bottom: 8px;
      color: var(--wc-accent);
      text-shadow: 0 0 12px var(--wc-accent);
    }
    #WC_SCOPE .wc-header h1 {
      font-size: 1.3rem;
      font-weight: 700;
      margin-bottom: 4px;
      letter-spacing: 0.05em;
      color: var(--wc-accent);
    }
    #WC_SCOPE .wc-header p {
      color: var(--wc-text-muted);
      font-size: 0.8rem;
    }
    #WC_SCOPE .wc-progress-bar {
      height: 3px;
      background: var(--wc-border-dim);
      position: relative;
    }
    #WC_SCOPE .wc-progress-fill {
      height: 100%;
      background: var(--wc-accent);
      transition: width var(--wc-transition);
      box-shadow: 0 0 8px var(--wc-accent);
    }
    #WC_SCOPE .wc-body {
      padding: 28px;
      min-height: 320px;
      display: flex;
      flex-direction: column;
      justify-content: center;
    }
    #WC_SCOPE .wc-step {
      display: none;
      animation: wc-fadeIn 0.3s ease;
    }
    #WC_SCOPE .wc-step.active { display: block; }
    @keyframes wc-fadeIn {
      from { opacity: 0; transform: translateY(8px); }
      to { opacity: 1; transform: translateY(0); }
    }
    #WC_SCOPE .wc-step-label {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      color: var(--wc-accent);
      margin-bottom: 10px;
      font-weight: 600;
    }
    #WC_SCOPE .wc-step-question {
      font-size: 1.1rem;
      font-weight: 600;
      margin-bottom: 24px;
      line-height: 1.5;
      color: var(--wc-text);
    }
    #WC_SCOPE .wc-options-grid {
      display: flex;
      flex-direction: column;
      gap: 8px;
    }
    #WC_SCOPE .wc-option-btn {
      width: 100%;
      padding: 14px 18px;
      background: var(--wc-bg);
      border: 1px solid var(--wc-border-dim);
      border-radius: var(--wc-radius);
      color: var(--wc-text);
      font-size: 0.9rem;
      text-align: left;
      cursor: pointer;
      transition: all var(--wc-transition);
      font-family: inherit;
    }
    #WC_SCOPE .wc-option-btn:hover {
      background: var(--wc-surface-hover);
      border-color: var(--wc-accent);
      box-shadow: 0 0 12px var(--wc-accent-glow);
    }
    #WC_SCOPE .wc-option-btn.selected {
      background: var(--wc-accent-glow);
      border-color: var(--wc-accent);
      color: var(--wc-accent);
      box-shadow: 0 0 16px var(--wc-accent-glow);
    }
    #WC_SCOPE .wc-scale-container {
      display: flex;
      gap: 6px;
      flex-wrap: wrap;
      justify-content: center;
    }
    #WC_SCOPE .wc-scale-btn {
      width: 42px;
      height: 42px;
      border-radius: var(--wc-radius);
      border: 1px solid var(--wc-border-dim);
      background: var(--wc-bg);
      color: var(--wc-text);
      font-size: 1rem;
      font-weight: 600;
      cursor: pointer;
      transition: all var(--wc-transition);
      font-family: inherit;
    }
    #WC_SCOPE .wc-scale-btn:hover {
      border-color: var(--wc-accent);
      box-shadow: 0 0 12px var(--wc-accent-glow);
    }
    #WC_SCOPE .wc-scale-btn.selected {
      background: var(--wc-accent);
      border-color: var(--wc-accent);
      color: var(--wc-bg);
      box-shadow: 0 0 20px var(--wc-accent-glow);
    }
    #WC_SCOPE .wc-scale-labels {
      display: flex;
      justify-content: space-between;
      margin-top: 8px;
      font-size: 0.75rem;
      color: var(--wc-text-muted);
    }
    #WC_SCOPE .wc-text-response {
      width: 100%;
      min-height: 100px;
      padding: 14px 18px;
      background: var(--wc-bg);
      border: 1px solid var(--wc-border-dim);
      border-radius: var(--wc-radius);
      color: var(--wc-text);
      font-size: 0.9rem;
      font-family: inherit;
      resize: vertical;
      transition: border-color var(--wc-transition);
    }
    #WC_SCOPE .wc-text-response:focus {
      outline: none;
      border-color: var(--wc-accent);
      box-shadow: 0 0 12px var(--wc-accent-glow);
    }
    #WC_SCOPE .wc-footer {
      padding: 18px 28px;
      border-top: 1px solid var(--wc-border-dim);
      display: flex;
      justify-content: space-between;
      align-items: center;
    }
    #WC_SCOPE .wc-nav-btn {
      padding: 10px 24px;
      border-radius: var(--wc-radius);
      font-size: 0.85rem;
      font-weight: 600;
      cursor: pointer;
      transition: all var(--wc-transition);
      font-family: inherit;
      border: 1px solid;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }
    #WC_SCOPE .wc-nav-btn.secondary {
      background: transparent;
      color: var(--wc-text-muted);
      border-color: var(--wc-border-dim);
    }
    #WC_SCOPE .wc-nav-btn.secondary:hover {
      color: var(--wc-text);
      border-color: var(--wc-text-muted);
    }
    #WC_SCOPE .wc-nav-btn.primary {
      background: var(--wc-accent);
      color: var(--wc-bg);
      border-color: var(--wc-accent);
      box-shadow: 0 0 16px var(--wc-accent-glow);
    }
    #WC_SCOPE .wc-nav-btn.primary:hover {
      box-shadow: 0 0 24px rgba(0, 255, 136, 0.3);
      transform: translateY(-1px);
    }
    #WC_SCOPE .wc-nav-btn:disabled {
      opacity: 0.3;
      cursor: not-allowed;
      transform: none;
      box-shadow: none;
    }
    #WC_SCOPE .wc-results-card { text-align: center; }
    #WC_SCOPE .wc-results-icon { font-size: 2.5rem; margin-bottom: 12px; text-shadow: 0 0 16px currentColor; }
    #WC_SCOPE .wc-results-title { font-size: 1.2rem; font-weight: 700; margin-bottom: 8px; color: var(--wc-accent); }
    #WC_SCOPE .wc-results-summary { color: var(--wc-text-muted); margin-bottom: 24px; font-size: 0.9rem; }
    #WC_SCOPE .wc-insight-box {
      background: var(--wc-bg);
      border: 1px solid var(--wc-border-dim);
      border-radius: var(--wc-radius);
      padding: 18px;
      margin-bottom: 16px;
      text-align: left;
    }
    #WC_SCOPE .wc-insight-box h4 {
      font-size: 0.7rem;
      text-transform: uppercase;
      letter-spacing: 0.1em;
      color: var(--wc-accent);
      margin-bottom: 8px;
    }
    #WC_SCOPE .wc-insight-box p { font-size: 0.85rem; color: var(--wc-text-muted); line-height: 1.7; }
    #WC_SCOPE .wc-resource-list { list-style: none; text-align: left; }
    #WC_SCOPE .wc-resource-list li {
      padding: 10px 14px;
      background: var(--wc-bg);
      border: 1px solid var(--wc-border-dim);
      border-radius: var(--wc-radius);
      margin-bottom: 6px;
      font-size: 0.85rem;
      display: flex;
      align-items: center;
      gap: 10px;
    }
    #WC_SCOPE .wc-resource-list li::before { content: "▶"; color: var(--wc-accent); font-size: 0.6rem; }
    #WC_SCOPE .wc-safety-note {
      background: rgba(255, 68, 68, 0.06);
      border: 1px solid rgba(255, 68, 68, 0.25);
      border-radius: var(--wc-radius);
      padding: 14px 18px;
      font-size: 0.8rem;
      color: var(--wc-danger);
      margin-top: 18px;
      text-align: left;
    }
    #WC_SCOPE .wc-safety-note strong { display: block; margin-bottom: 4px; }
    #WC_SCOPE .wc-glow-text { color: var(--wc-accent); }
    @media (prefers-reduced-motion: reduce) {
      #WC_SCOPE * { animation-duration: 0.01ms !important; transition-duration: 0.01ms !important; }
    }
    @media (max-width: 480px) {
      #WC_SCOPE .wc-body { padding: 20px; }
      #WC_SCOPE .wc-header { padding: 20px; }
      #WC_SCOPE .wc-footer { padding: 14px 20px; }
      #WC_SCOPE .wc-scale-btn { width: 36px; height: 36px; font-size: 0.9rem; }
    }
  `;

  const STEPS = [
    {
      label: 'Step 1 of 7',
      question: 'How would you rate your overall mood right now?',
      type: 'scale',
      options: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      lowLabel: 'Very low',
      highLabel: 'Excellent',
      key: 'mood'
    },
    {
      label: 'Step 2 of 7',
      question: 'Over the past week, how often have you felt overwhelmed by your responsibilities?',
      type: 'choice',
      options: [
        { value: 'never', label: 'Rarely or never — I\'ve been managing fine' },
        { value: 'sometimes', label: 'Sometimes — occasional pressure spikes' },
        { value: 'often', label: 'Often — most days feel like a struggle' },
        { value: 'always', label: 'Constantly — I can\'t seem to catch up' }
      ],
      key: 'overwhelm'
    },
    {
      label: 'Step 3 of 7',
      question: 'How has your sleep been lately?',
      type: 'choice',
      options: [
        { value: 'good', label: 'Restful — I wake up feeling restored' },
        { value: 'okay', label: 'Decent — some rough nights but manageable' },
        { value: 'poor', label: 'Disrupted — trouble falling or staying asleep' },
        { value: 'bad', label: 'Severe — insomnia or sleeping too much' }
      ],
      key: 'sleep'
    },
    {
      label: 'Step 4 of 7',
      question: 'Which thought pattern sounds most familiar right now?',
      type: 'choice',
      options: [
        { value: 'catastrophizing', label: '"Everything is going to fall apart"' },
        { value: 'all_or_nothing', label: '"If I can\'t do it perfectly, there\'s no point"' },
        { value: 'mind_reading', label: '"They probably think I\'m incompetent"' },
        { value: 'should_statements', label: '"I should be handling this better"' },
        { value: 'none', label: 'None of these resonate' }
      ],
      key: 'thought_pattern'
    },
    {
      label: 'Step 5 of 7',
      question: 'How connected do you feel to others around you?',
      type: 'scale',
      options: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      lowLabel: 'Very isolated',
      highLabel: 'Deeply connected',
      key: 'connection'
    },
    {
      label: 'Step 6 of 7',
      question: 'What\'s one thing you\'ve been avoiding that weighs on you?',
      type: 'text',
      placeholder: 'Type your response here (completely private — nothing is saved)...',
      key: 'avoidance'
    },
    {
      label: 'Step 7 of 7',
      question: 'On a scale of 1-10, how motivated do you feel to take one small step toward feeling better?',
      type: 'scale',
      options: [1, 2, 3, 4, 5, 6, 7, 8, 9, 10],
      lowLabel: 'Not at all',
      highLabel: 'Very motivated',
      key: 'motivation'
    }
  ];

  const PATTERN_NAMES = {
    catastrophizing: 'Catastrophizing',
    all_or_nothing: 'All-or-nothing thinking',
    mind_reading: 'Mind reading',
    'should_statements': '"Should" statements'
  };

  const PATTERN_ADVICE = {
    catastrophizing: 'When you notice "everything is going to fall apart," try asking: "What\'s the most likely outcome, not the worst case?"',
    all_or_nothing: 'Perfectionism is a harsh master. Try: "What would \'good enough\' look like here?" Progress, not perfection.',
    mind_reading: 'You can\'t know what others think. Try: "What evidence do I actually have for that belief?"',
    'should_statements': '"Should" creates guilt. Replace with "I\'d prefer to…" or "I choose to…" — it returns agency to you.'
  };

  function injectStyles() {
    if (document.getElementById(STYLE_ID)) return;
    const style = document.createElement('style');
    style.id = STYLE_ID;
    style.textContent = CSS;
    document.head.appendChild(style);
  }

  function init(targetEl) {
    const container = typeof targetEl === 'string' ? document.getElementById(targetEl) : targetEl;
    if (!container) {
      console.error('[Wellness Check-In] Target element not found:', targetEl);
      return;
    }

    injectStyles();
    container.id = 'WC_SCOPE';

    // Build structure
    container.innerHTML = `
      <div class="wc-header">
        <div class="wc-icon">⬡</div>
        <h1>Wellness Check-In</h1>
        <p>A brief, private self-assessment — no data stored, no judgment.</p>
      </div>
      <div class="wc-progress-bar">
        <div class="wc-progress-fill" id="wc-progressFill" style="width: 14%"></div>
      </div>
      <div class="wc-body" id="wc-body"></div>
      <div class="wc-footer">
        <button class="wc-nav-btn secondary" id="wc-btnBack" disabled>◀ Back</button>
        <button class="wc-nav-btn primary" id="wc-btnNext">Continue ▶</button>
      </div>
    `;

    const body = document.getElementById('wc-body');
    const btnBack = document.getElementById('wc-btnBack');
    const btnNext = document.getElementById('wc-btnNext');
    const progressFill = document.getElementById('wc-progressFill');

    let currentStep = 0;
    const responses = {};

    function renderStep() {
      const step = STEPS[currentStep];
      progressFill.style.width = ((currentStep + 1) / STEPS.length * 100) + '%';
      btnBack.disabled = currentStep === 0;

      let html = '<div class="wc-step active" data-index="' + currentStep + '">';
      html += '<div class="wc-step-label">' + step.label + '</div>';
      html += '<div class="wc-step-question">' + step.question + '</div>';

      if (step.type === 'scale') {
        html += '<div class="wc-scale-container">';
        step.options.forEach(v => {
          const selected = responses[step.key] === v ? ' selected' : '';
          html += '<button class="wc-scale-btn' + selected + '" data-value="' + v + '">' + v + '</button>';
        });
        html += '</div>';
        html += '<div class="wc-scale-labels"><span>' + step.lowLabel + '</span><span>' + step.highLabel + '</span></div>';
      } else if (step.type === 'choice') {
        html += '<div class="wc-options-grid">';
        step.options.forEach(opt => {
          const selected = responses[step.key] === opt.value ? ' selected' : '';
          html += '<button class="wc-option-btn' + selected + '" data-value="' + opt.value + '">' + opt.label + '</button>';
        });
        html += '</div>';
      } else if (step.type === 'text') {
        html += '<textarea class="wc-text-response" id="wc-textInput" placeholder="' + step.placeholder + '">' + (responses[step.key] || '') + '</textarea>';
      }

      html += '</div>';
      body.innerHTML = html;
      attachListeners();
      updateNextButton();
    }

    function attachListeners() {
      const step = STEPS[currentStep];
      if (step.type === 'scale') {
        body.querySelectorAll('.wc-scale-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            body.querySelectorAll('.wc-scale-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            responses[step.key] = parseInt(btn.dataset.value);
            updateNextButton();
          });
        });
      } else if (step.type === 'choice') {
        body.querySelectorAll('.wc-option-btn').forEach(btn => {
          btn.addEventListener('click', () => {
            body.querySelectorAll('.wc-option-btn').forEach(b => b.classList.remove('selected'));
            btn.classList.add('selected');
            responses[step.key] = btn.dataset.value;
            updateNextButton();
          });
        });
      } else if (step.type === 'text') {
        const textarea = document.getElementById('wc-textInput');
        textarea.addEventListener('input', () => {
          responses[step.key] = textarea.value;
          updateNextButton();
        });
      }
    }

    function updateNextButton() {
      const step = STEPS[currentStep];
      const hasResponse = responses[step.key] !== undefined && responses[step.key] !== '';
      btnNext.disabled = !hasResponse;
      btnNext.textContent = currentStep === STEPS.length - 1 ? 'See Results ▶' : 'Continue ▶';
    }

    function renderResults() {
      progressFill.style.width = '100%';
      btnBack.style.display = 'none';
      btnNext.style.display = 'none';

      const mood = responses.mood || 5;
      const connection = responses.connection || 5;
      const motivation = responses.motivation || 5;
      const thoughtPattern = responses.thought_pattern;
      const overwhelm = responses.overwhelm;
      const sleep = responses.sleep;

      let icon = '⬡';
      let title = 'You\'re holding steady';
      let summary = 'Your responses suggest you\'re managing, with some areas worth attention.';

      if (mood <= 3 || (overwhelm === 'always' && sleep === 'bad')) {
        icon = '◈';
        title = 'Things feel heavy right now';
        summary = 'Your responses suggest you\'re going through a genuinely difficult stretch. That takes courage to acknowledge.';
      } else if (mood >= 7 && connection >= 6) {
        icon = '◇';
        title = 'You\'re in a good place';
        summary = 'Your responses suggest solid wellbeing across multiple areas. Keep doing what\'s working.';
      }

      let html = '<div class="wc-step active wc-results-card">';
      html += '<div class="wc-results-icon">' + icon + '</div>';
      html += '<div class="wc-results-title">' + title + '</div>';
      html += '<div class="wc-results-summary">' + summary + '</div>';

      if (thoughtPattern && thoughtPattern !== 'none') {
        html += '<div class="wc-insight-box"><h4>Pattern Noticed: <span class="wc-glow-text">' + PATTERN_NAMES[thoughtPattern] + '</span></h4><p>' + PATTERN_ADVICE[thoughtPattern] + '</p></div>';
      }

      if (responses.avoidance && responses.avoidance.trim().length > 0) {
        html += '<div class="wc-insight-box"><h4>On Avoidance</h4><p>You mentioned something you\'ve been avoiding. Here\'s a reframe: <strong class="wc-glow-text">you don\'t have to solve it today.</strong> What\'s one 5-minute action you could take toward it this week? Not to fix it — just to stop running from it.</p></div>';
      }

      html += '<div class="wc-insight-box"><h4>Suggested Next Steps</h4><ul class="wc-resource-list">';
      if (sleep === 'poor' || sleep === 'bad') {
        html += '<li>Try a consistent wind-down routine 30 minutes before bed — no screens, dim lights</li>';
      }
      if (overwhelm === 'often' || overwhelm === 'always') {
        html += '<li>Write down your top 3 priorities for tomorrow tonight — externalize the mental load</li>';
      }
      if (connection <= 4) {
        html += '<li>Reach out to one person today — even a brief text counts as connection</li>';
      }
      if (mood <= 4) {
        html += '<li>Try the 5-4-3-2-1 grounding technique: name 5 things you see, 4 you hear, 3 you can touch, 2 you smell, 1 you taste</li>';
      }
      if (motivation >= 6) {
        html += '<li>Your motivation is present — channel it into one small, concrete action within the next hour</li>';
      }
      html += '<li>Journal for 5 minutes: "What would I tell a close friend who was feeling this way?"</li>';
      html += '</ul></div>';

      html += '<div class="wc-safety-note"><strong>⚠ Important</strong>This is a self-assessment tool, not a diagnosis. If you\'re having thoughts of self-harm or feel you\'re in crisis, please contact a licensed professional or call/text <strong>988</strong> (Suicide & Crisis Lifeline) immediately. You deserves support.</div>';

      html += '</div>';
      body.innerHTML = html;
    }

    btnNext.addEventListener('click', () => {
      if (currentStep < STEPS.length - 1) {
        currentStep++;
        renderStep();
      } else {
        renderResults();
      }
    });

    btnBack.addEventListener('click', () => {
      if (currentStep > 0) {
        currentStep--;
        renderStep();
      }
    });

    renderStep();
  }

  // Expose global API
  window.initWellnessCheckin = init;

  // Auto-init on elements with data attribute
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', autoInit);
  } else {
    autoInit();
  }

  function autoInit() {
    document.querySelectorAll('[data-wellness-checkin]').forEach(el => {
      init(el);
    });
  }
})();
