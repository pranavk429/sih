#!/usr/bin/env python3
"""
Render ultra-premium, tier-1 tech deck HTML preview of SIH 2026 Idea PPT
and export 1600x900 PNG slides to ppt-preview/ using Playwright.
"""

import asyncio
import os
from playwright.async_api import async_playwright

HTML_CONTENT = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<title>SIH 2026 Idea Submission Deck — Executive Edition</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Plus+Jakarta+Sans:wght@400;500;600;700;800&family=Outfit:wght@500;600;700;800&family=JetBrains+Mono:wght@500;700&display=swap" rel="stylesheet">
<style>
  :root {
    --navy-dark: #0B192C;
    --navy-primary: #1E3E62;
    --navy-header: #1F497D;
    --blue-accent: #0070C0;
    --blue-bright: #0284C7;
    --blue-light: #E0F2FE;
    --red-alert: #DC2626;
    --red-soft: #FEF2F2;
    --red-border: #FECACA;
    --green-success: #16A34A;
    --green-soft: #F0FDF4;
    --green-border: #BBF7D0;
    --amber-warning: #D97706;
    --amber-soft: #FFFBEB;
    --amber-border: #FDE68A;
    --card-bg: #F8FAFC;
    --card-border: #E2E8F0;
    --text-main: #0F172A;
    --text-muted: #64748B;
    --text-sub: #475569;
  }

  * { box-sizing: border-box; margin: 0; padding: 0; }
  body {
    background: #090D14;
    font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    padding: 40px 20px;
    gap: 48px;
    color: var(--text-main);
  }
  
  .slide-container {
    width: 1333.33px;
    height: 750px;
    position: relative;
    background: #FFFFFF;
    overflow: hidden;
    box-shadow: 0 25px 50px -12px rgba(0, 0, 0, 0.45), 0 0 0 1px rgba(255, 255, 255, 0.1);
    border-radius: 6px;
    flex-shrink: 0;
  }
  
  /* Template Elements */
  .tpl-logo {
    position: absolute;
    top: 6px;
    right: 24px;
    width: 230px;
    height: 105px;
    z-index: 20;
    background-image: url('assets/slide_1_Picture 1_1.png');
    background-size: contain;
    background-repeat: no-repeat;
    filter: drop-shadow(0 2px 4px rgba(0,0,0,0.05));
  }
  
  .tpl-oval {
    position: absolute;
    top: 20px;
    left: 36px;
    width: 132px;
    height: 74px;
    border-radius: 9999px;
    background: linear-gradient(135deg, #1E3E62 0%, #0070C0 100%);
    color: #FFFFFF;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    font-family: 'Outfit', sans-serif;
    font-size: 13px;
    font-weight: 700;
    text-align: center;
    padding: 6px 12px;
    z-index: 20;
    border: 2px solid #FFFFFF;
    box-shadow: 0 4px 12px rgba(0, 112, 192, 0.25);
    letter-spacing: 0.2px;
  }
  
  .tpl-footer-bar {
    position: absolute;
    bottom: 0;
    left: 0;
    width: 100%;
    height: 52px;
    background: linear-gradient(90deg, #1F497D 0%, #0070C0 100%);
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 44px;
    color: #FFFFFF;
    font-size: 13.5px;
    font-weight: 600;
    z-index: 20;
    letter-spacing: 0.3px;
  }
  .tpl-footer-bar .badge-footer {
    background: rgba(255, 255, 255, 0.2);
    padding: 3px 12px;
    border-radius: 9999px;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
  }
  
  /* Slide Top Header Bar */
  .slide-header-title {
    position: absolute;
    top: 24px;
    left: 188px;
    font-family: 'Outfit', sans-serif;
    font-size: 27px;
    font-weight: 800;
    color: var(--navy-header);
    letter-spacing: -0.3px;
    display: flex;
    align-items: center;
    gap: 12px;
  }
  .slide-header-tagline {
    font-family: 'Plus Jakarta Sans', sans-serif;
    font-size: 13.5px;
    font-weight: 600;
    color: var(--blue-accent);
    font-style: italic;
    letter-spacing: 0px;
  }
  
  /* Safe Content Area */
  .content-area {
    position: absolute;
    top: 110px;
    left: 36px;
    width: 1261px;
    height: 574px;
    z-index: 10;
  }
  
  /* Modern Section Bar */
  .section-bar {
    background: linear-gradient(90deg, #1F497D 0%, #1E3E62 100%);
    color: #FFFFFF;
    font-family: 'Outfit', sans-serif;
    font-weight: 700;
    font-size: 12.5px;
    letter-spacing: 0.8px;
    text-transform: uppercase;
    padding: 6px 14px;
    border-radius: 6px;
    display: flex;
    align-items: center;
    gap: 8px;
    box-shadow: 0 2px 6px rgba(31, 73, 125, 0.15);
  }
  .section-bar::before {
    content: "";
    display: inline-block;
    width: 4px;
    height: 12px;
    background: #00E5FF;
    border-radius: 2px;
  }
  
  /* Bento Cards */
  .bento-card {
    background: #FFFFFF;
    border: 1px solid var(--card-border);
    border-radius: 8px;
    box-shadow: 0 2px 8px rgba(15, 23, 42, 0.04);
    position: relative;
    overflow: hidden;
  }
  .bento-card-tint {
    background: #F8FAFC;
    border: 1px solid #E2E8F0;
  }
  
  /* Status Tag Chips */
  .chip {
    display: inline-flex;
    align-items: center;
    gap: 5px;
    padding: 3px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
    letter-spacing: 0.3px;
    text-transform: uppercase;
  }
  .chip-blue { background: #E0F2FE; color: #0369A1; border: 1px solid #BAE6FD; }
  .chip-navy { background: #E2E8F0; color: #1E293B; border: 1px solid #CBD5E1; }
  .chip-green { background: #DCFCE7; color: #15803D; border: 1px solid #BBF7D0; }
  .chip-red { background: #FEE2E2; color: #B91C1C; border: 1px solid #FECACA; }
  .chip-amber { background: #FEF3C7; color: #B45309; border: 1px solid #FDE68A; }

  /* Flow Step Card */
  .step-card {
    flex: 1;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 8px;
    padding: 10px 12px;
    display: flex;
    flex-direction: column;
    gap: 6px;
    position: relative;
    box-shadow: 0 2px 6px rgba(0, 0, 0, 0.03);
    transition: transform 0.2s ease;
  }
  .step-card::before {
    content: "";
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    height: 3px;
  }
  .step-card.c-blue::before { background: #0070C0; }
  .step-card.c-navy::before { background: #1F497D; }
  .step-card.c-amber::before { background: #D97706; }
  .step-card.c-green::before { background: #16A34A; }
  
  .step-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .step-num {
    font-family: 'JetBrains Mono', monospace;
    font-size: 11px;
    font-weight: 700;
  }
  .step-title {
    font-family: 'Outfit', sans-serif;
    font-size: 13px;
    font-weight: 800;
    letter-spacing: 0.4px;
  }
  .step-desc {
    font-size: 11.5px;
    color: var(--text-sub);
    line-height: 1.35;
    font-weight: 500;
  }

  /* Sleek Comparison Table */
  .cmp-table {
    width: 100%;
    border-collapse: separate;
    border-spacing: 0 4px;
  }
  .cmp-table th {
    font-family: 'Outfit', sans-serif;
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 8px 12px;
    border-radius: 4px;
  }
  .cmp-table td {
    padding: 9px 12px;
    font-size: 11.8px;
    line-height: 1.35;
    vertical-align: middle;
  }
  .cmp-row-left {
    background: #F1F5F9;
    color: #475569;
    font-weight: 500;
    border-radius: 6px 0 0 6px;
    border-left: 3px solid #94A3B8;
  }
  .cmp-row-right {
    background: #EFF6FF;
    color: #1E3E62;
    font-weight: 700;
    border-radius: 0 6px 6px 0;
    border-right: 3px solid #0070C0;
  }

  /* Slide 1 Styles */
  .s1-hero-card {
    position: absolute;
    top: 130px;
    left: 36px;
    width: 710px;
    height: 540px;
    background: #FFFFFF;
    border: 1px solid #CBD5E1;
    border-radius: 12px;
    box-shadow: 0 10px 30px rgba(15, 23, 42, 0.08);
    overflow: hidden;
    display: flex;
    flex-direction: column;
  }
  .s1-header {
    background: linear-gradient(135deg, #1F497D 0%, #0F2A4A 100%);
    padding: 16px 24px;
    color: #FFFFFF;
    display: flex;
    align-items: center;
    justify-content: space-between;
  }
  .s1-row {
    padding: 12px 24px;
    border-bottom: 1px solid #F1F5F9;
    display: flex;
    align-items: flex-start;
  }
  .s1-lbl {
    width: 230px;
    font-family: 'Outfit', sans-serif;
    font-size: 14px;
    font-weight: 700;
    color: var(--navy-header);
    flex-shrink: 0;
  }
  .s1-val {
    font-size: 14px;
    font-weight: 600;
    color: var(--text-main);
  }
  .s1-val-hl {
    color: var(--blue-accent);
    font-family: 'JetBrains Mono', monospace;
    font-weight: 700;
    background: #EFF6FF;
    padding: 2px 8px;
    border-radius: 4px;
    border: 1px solid #BFDBFE;
  }
</style>
</head>
<body>

<!-- ====================================================
     SLIDE 1: Title Page
     ==================================================== -->
<div class="slide-container" id="slide-1">
  <!-- Template Blue Polygon -->
  <div style="position: absolute; top: 0; left: 240px; width: 1093px; height: 750px; background: linear-gradient(135deg, #0070C0 0%, #0A4D80 100%); clip-path: polygon(10% 0, 100% 0, 100% 100%, 0% 100%);"></div>
  <div class="tpl-logo"></div>
  <div style="position: absolute; top: 160px; right: 60px; width: 440px; height: 440px; background-image: url('assets/slide_1_Picture 4_0.png'); background-size: contain; background-repeat: no-repeat; z-index: 5; filter: drop-shadow(0 12px 24px rgba(0,0,0,0.25));"></div>
  
  <div style="position: absolute; top: 40px; left: 36px; z-index: 10;">
    <div style="font-family: 'Outfit', sans-serif; font-size: 13px; font-weight: 800; color: #0070C0; letter-spacing: 1.5px; text-transform: uppercase;">
      Official Presentation Deck
    </div>
    <div style="font-family: 'Outfit', sans-serif; font-size: 32px; font-weight: 800; color: #1F497D; letter-spacing: -0.5px;">
      SMART INDIA HACKATHON 2026
    </div>
  </div>

  <div class="s1-hero-card" style="z-index: 10;">
    <div class="s1-header">
      <div style="display: flex; align-items: center; gap: 8px;">
        <span style="display: inline-block; width: 8px; height: 8px; border-radius: 50%; background: #00E5FF;"></span>
        <span style="font-family: 'Outfit', sans-serif; font-size: 14px; font-weight: 700; letter-spacing: 0.6px; text-transform: uppercase;">
          Idea Submission Details · Pre-Screening
        </span>
      </div>
      <span class="chip chip-blue" style="font-family: 'JetBrains Mono', monospace; font-size: 11px; background: rgba(255,255,255,0.15); color: #FFFFFF; border: none;">
        STAGE 1 DRAFT
      </span>
    </div>

    <div style="flex: 1; display: flex; flex-direction: column; justify-content: space-between; padding: 6px 0;">
      <div class="s1-row">
        <div class="s1-lbl">Problem Statement ID</div>
        <div class="s1-val" style="font-family: 'JetBrains Mono', monospace; font-size: 17px; font-weight: 800; color: #0070C0;">
          SIH26104
        </div>
      </div>
      <div class="s1-row">
        <div class="s1-lbl">Problem Statement Title</div>
        <div class="s1-val" style="font-weight: 700; color: #0F172A; line-height: 1.35;">
          AI-Powered Real-Time Detection and Prevention of Voice Cloning Impersonation Attacks
        </div>
      </div>
      <div class="s1-row">
        <div class="s1-lbl">Theme</div>
        <div class="s1-val">
          <span class="chip chip-navy" style="font-size: 12px; text-transform: none;">Miscellaneous</span>
        </div>
      </div>
      <div class="s1-row">
        <div class="s1-lbl">PS Category</div>
        <div class="s1-val">
          <span class="chip chip-blue" style="font-size: 12px; text-transform: none;">Software</span>
        </div>
      </div>
      <div class="s1-row">
        <div class="s1-lbl">Team ID</div>
        <div class="s1-val"><span class="s1-val-hl">[FILL]</span></div>
      </div>
      <div class="s1-row">
        <div class="s1-lbl">Registered Team Name</div>
        <div class="s1-val"><span class="s1-val-hl">[FILL]</span></div>
      </div>
    </div>

    <div style="background: #F8FAFC; border-top: 1px solid #E2E8F0; padding: 12px 24px; font-size: 12px; color: #64748B; display: flex; justify-content: space-between; align-items: center;">
      <span><strong>Organisation:</strong> AICTE · Software Track</span>
      <span style="font-family: 'JetBrains Mono', monospace; font-size: 11px;">PORTAL CAP: 500 TEAMS</span>
    </div>
  </div>
</div>

<!-- ====================================================
     SLIDE 2: Idea Title / Proposed Solution (The 50pt Carrier)
     ==================================================== -->
<div class="slide-container" id="slide-2">
  <div class="tpl-oval">YOUR TEAM<br>LOGO</div>
  <div class="tpl-logo"></div>
  <div class="tpl-footer-bar">
    <span>@SIH Idea submission - Template</span>
    <span class="badge-footer">SLIDE 02</span>
  </div>
  
  <div class="slide-header-title">
    <span>[ YOUR IDEA NAME ]</span>
    <span class="slide-header-tagline">— "Verify the speaker, don't just guess at the audio."</span>
  </div>
  
  <div class="content-area" style="display: flex; flex-direction: column; gap: 10px;">
    <!-- Section 1 Header -->
    <div class="section-bar">Proposed Solution — Detailed Explanation</div>
    
    <!-- Executive Lead-in Callout -->
    <div style="background: #EFF6FF; border-left: 4px solid #0070C0; padding: 7px 14px; border-radius: 4px; font-size: 12px; color: #1E3E62; line-height: 1.4;">
      <strong style="color: #0F172A;">A Tiered Voice-Integrity Gate for High-Stakes Telephony:</strong>
      Verify enrolled speakers directly, trigger compute-heavy countermeasure models only when financial or credential access is at stake, and output verifiable cryptographic evidence rather than an uninterpretable probability score.
    </div>
    
    <!-- 4-Stage Bento Flow -->
    <div style="display: flex; align-items: center; gap: 8px;">
      <!-- Step 1 -->
      <div class="step-card c-blue">
        <div class="step-header">
          <span class="step-title" style="color: #0070C0;">TRIGGER</span>
          <span class="chip chip-blue" style="font-size: 9.5px;">STAGE 01</span>
        </div>
        <div class="step-desc">
          Always-on, low-power intent classifier. Wakes on fund transfers, OTP requests, and urgency + authority pressure.
        </div>
      </div>
      <div style="color: #94A3B8; font-size: 16px; font-weight: 800;">➔</div>
      
      <!-- Step 2 -->
      <div class="step-card c-navy">
        <div class="step-header">
          <span class="step-title" style="color: #1F497D;">VERIFY</span>
          <span class="chip chip-navy" style="font-size: 9.5px;">STAGE 02</span>
        </div>
        <div class="step-desc">
          Enrolled voice on file? Direct speaker verification. Branches between synthetic TTS and live voice conversion (RVC).
        </div>
      </div>
      <div style="color: #94A3B8; font-size: 16px; font-weight: 800;">➔</div>
      
      <!-- Step 3 -->
      <div class="step-card c-amber">
        <div class="step-header">
          <span class="step-title" style="color: #D97706;">CHALLENGE</span>
          <span class="chip chip-amber" style="font-size: 9.5px;">STAGE 03</span>
        </div>
        <div class="step-desc">
          Ambiguous match? System injects a zero-latency conversational prompt. Turns passive detection into active prevention.
        </div>
      </div>
      <div style="color: #94A3B8; font-size: 16px; font-weight: 800;">➔</div>
      
      <!-- Step 4 -->
      <div class="step-card c-green">
        <div class="step-header">
          <span class="step-title" style="color: #16A34A;">EVIDENCE</span>
          <span class="chip chip-green" style="font-size: 9.5px;">STAGE 04</span>
        </div>
        <div class="step-desc">
          Produces timestamped anomaly breakdown & tamper-proof audit log. Mathematical features only — zero raw audio stored.
        </div>
      </div>
    </div>
    
    <!-- 2 Column Lower Bento Grid -->
    <div style="display: flex; gap: 14px; flex: 1;">
      <!-- Left Column: How it addresses problem -->
      <div style="width: 440px; display: flex; flex-direction: column; gap: 8px;">
        <div class="section-bar" style="font-size: 11.5px;">How It Addresses The Problem</div>
        <div class="bento-card" style="flex: 1; padding: 10px 14px; display: flex; flex-direction: column; justify-content: space-between;">
          <div style="display: flex; flex-direction: column; gap: 5px;">
            <div style="display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 700; color: #16A34A;">
              <span style="background: #DCFCE7; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px;">✓</span>
              <span>Multi-layer voice authenticity analysis</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 700; color: #16A34A;">
              <span style="background: #DCFCE7; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px;">✓</span>
              <span>Real-time risk scoring engine (near zero-latency)</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 700; color: #16A34A;">
              <span style="background: #DCFCE7; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px;">✓</span>
              <span>Alerting & interactive user intervention layer</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 700; color: #16A34A;">
              <span style="background: #DCFCE7; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px;">✓</span>
              <span>Privacy by design: Edge inference, DPDP compliance</span>
            </div>
            <div style="display: flex; align-items: center; gap: 8px; font-size: 11.5px; font-weight: 700; color: #16A34A;">
              <span style="background: #DCFCE7; width: 18px; height: 18px; border-radius: 50%; display: flex; align-items: center; justify-content: center; font-size: 10px;">✓</span>
              <span>Telephony-ready (SIP/RTP), multilingual Indic speech</span>
            </div>
          </div>
          
          <div style="background: #FFFBEB; border: 1px solid #FDE68A; border-radius: 6px; padding: 8px 10px; margin-top: 6px;">
            <div style="display: flex; align-items: center; gap: 6px; color: #B45309; font-weight: 800; font-size: 11.5px;">
              <span>⚡</span> The Clause Most Teams Will Skip
            </div>
            <div style="font-size: 10.5px; color: #475569; line-height: 1.35; margin-top: 2px;">
              The PS buries speaker enrolment in a single sub-bullet. Centering our architecture around enrolment creates an unbreachable defense that sidesteps open-world blind detection traps.
            </div>
          </div>
        </div>
      </div>
      
      <!-- Right Column: Innovation & Uniqueness Matrix -->
      <div style="flex: 1; display: flex; flex-direction: column; gap: 8px;">
        <div class="section-bar" style="font-size: 11.5px;">Innovation & Uniqueness Matrix (25 + 25 Pts)</div>
        <div class="bento-card" style="flex: 1; padding: 6px 10px;">
          <table class="cmp-table">
            <thead>
              <tr>
                <th style="background: #F1F5F9; color: #64748B; width: 44%;">Status Quo / Naive Detector</th>
                <th style="background: #1E3E62; color: #FFFFFF; width: 56%;">Our Breakthrough Approach</th>
              </tr>
            </thead>
            <tbody>
              <tr>
                <td class="cmp-row-left">"Is this audio fake?" (Open-world blind guess)</td>
                <td class="cmp-row-right">"Is this the person we enrolled?" (~10–20× lower error)</td>
              </tr>
              <tr>
                <td class="cmp-row-left">Score every single second of every call</td>
                <td class="cmp-row-right">Semantic trigger wakes deep models on stakes — kills fatigue</td>
              </tr>
              <tr>
                <td class="cmp-row-left">Single generic detector for all attacks</td>
                <td class="cmp-row-right">Two-branch defense: Robot TTS vs. Live Human Puppeteer (RVC)</td>
              </tr>
              <tr>
                <td class="cmp-row-left">Overconfident probability number, always</td>
                <td class="cmp-row-right">Honest "Unsure — escalate to secondary MFA" when weak</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ====================================================
     SLIDE 3: Technical Approach
     ==================================================== -->
<div class="slide-container" id="slide-3">
  <div class="tpl-oval">YOUR TEAM<br>LOGO</div>
  <div class="tpl-logo"></div>
  <div class="tpl-footer-bar">
    <span>@SIH Idea submission - Template</span>
    <span class="badge-footer">SLIDE 03</span>
  </div>
  
  <div class="slide-header-title">
    <span>TECHNICAL APPROACH</span>
    <span class="slide-header-tagline">— Architected for real telephony and edge constraints</span>
  </div>
  
  <div class="content-area" style="display: flex; gap: 16px;">
    <!-- Left Column: Stack & Shippability -->
    <div style="width: 530px; display: flex; flex-direction: column; gap: 10px;">
      <div class="section-bar">Technologies To Be Used</div>
      
      <div class="bento-card" style="flex: 1; padding: 12px 16px; display: flex; flex-direction: column; justify-content: space-between; font-size: 11.5px;">
        <div style="display: grid; grid-template-columns: 110px 1fr; gap: 6px 10px; align-items: baseline;">
          <span class="chip chip-navy">Speech AI</span>
          <span style="color: #1E293B;"><strong>wav2vec2-XLSR</strong> multilingual encoder + <strong>ECAPA-TDNN</strong> speaker embeddings</span>
          
          <span class="chip chip-blue">Verification</span>
          <span style="color: #1E293B;">Learned fusion of enrolled-reference cosine distance + spoof countermeasure</span>
          
          <span class="chip chip-amber">Trigger Layer</span>
          <span style="color: #1E293B;">Lightweight streaming keyword/intent model over transcript (Whisper-small)</span>
          
          <span class="chip chip-green">Serving/Edge</span>
          <span style="color: #1E293B;"><strong>ONNX Runtime INT8 quantised</strong> — verifiable on-device edge execution</span>
          
          <span class="chip chip-navy">Telephony</span>
          <span style="color: #1E293B;">WebRTC / SIP via Asterisk; live RTP stream frame-by-frame analysis</span>
          
          <span class="chip chip-blue">Build & GPU</span>
          <span style="color: #1E293B;">PyTorch, FastAPI; free GPU compute via <strong>IndiaAI Portal</strong> / Kaggle</span>
        </div>
      </div>
      
      <!-- Android Callout -->
      <div style="background: #FFFBEB; border: 1.5px solid #F59E0B; border-radius: 8px; padding: 10px 14px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 3px;">
          <strong style="color: #B45309; font-size: 12px;">⚠️ Platform Constraint We Designed Around</strong>
          <span class="chip chip-amber" style="font-size: 9px;">SHIPPABILITY</span>
        </div>
        <div style="font-size: 10.8px; color: #475569; line-height: 1.35;">
          Android OS strictly blocks call-audio recording APIs (Android 10+, patched 2022). Consumer dialer apps claiming to intercept cell calls are unshippable. Our system deploys inside the <strong>VoIP/SIP & Enterprise contact center path</strong>, where it is fully legal and controllable.
        </div>
      </div>
      
      <!-- Offline Demo Callout -->
      <div style="background: #EFF6FF; border: 1.5px solid #0284C7; border-radius: 8px; padding: 10px 14px;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 3px;">
          <strong style="color: #0369A1; font-size: 12px;">🛡️ Guaranteed Venue-Proof Demo</strong>
          <span class="chip chip-blue" style="font-size: 9px;">100% OFFLINE</span>
        </div>
        <div style="font-size: 10.8px; color: #475569; line-height: 1.35;">
          Two laptops connected over local SIP server. We clone a volunteer's voice with open-source tools, initiate the call, and trigger live challenge/evidence with <strong>venue WiFi disconnected</strong>.
        </div>
      </div>
    </div>
    
    <!-- Right Column: Pipeline & Telephony Hardening -->
    <div style="flex: 1; display: flex; flex-direction: column; gap: 10px;">
      <div class="section-bar">Methodology & Process For Implementation</div>
      
      <!-- 4 Stacked Process Rows -->
      <div style="display: flex; flex-direction: column; gap: 8px;">
        <div style="display: flex; gap: 10px; align-items: stretch;">
          <div style="width: 120px; background: #0070C0; color: #FFFFFF; font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 12px; border-radius: 6px; display: flex; align-items: center; justify-content: center; letter-spacing: 0.5px;">
            1. TRIGGER
          </div>
          <div class="bento-card" style="flex: 1; padding: 8px 12px; font-size: 11.2px; color: #334155; line-height: 1.35;">
            Always-on, ultra-low compute listener. Buffers transcript and fires only when high-stakes keywords (wire transfer, password, urgency) are detected.
          </div>
        </div>
        
        <div style="display: flex; gap: 10px; align-items: stretch;">
          <div style="width: 120px; background: #1F497D; color: #FFFFFF; font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 12px; border-radius: 6px; display: flex; align-items: center; justify-content: center; letter-spacing: 0.5px;">
            2. VERIFY
          </div>
          <div class="bento-card" style="flex: 1; padding: 8px 12px; font-size: 11.2px; color: #334155; line-height: 1.35;">
            Enrolled reference exists → direct speaker match. Unenrolled → general countermeasure + honest low-confidence flag. Differentiates TTS vs. RVC.
          </div>
        </div>
        
        <div style="display: flex; gap: 10px; align-items: stretch;">
          <div style="width: 120px; background: #D97706; color: #FFFFFF; font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 12px; border-radius: 6px; display: flex; align-items: center; justify-content: center; letter-spacing: 0.5px;">
            3. CHALLENGE
          </div>
          <div class="bento-card" style="flex: 1; padding: 8px 12px; font-size: 11.2px; color: #334155; line-height: 1.35;">
            Suspicious score triggers unexpected audio challenge prompts or secondary MFA escalation before transactions complete.
          </div>
        </div>
        
        <div style="display: flex; gap: 10px; align-items: stretch;">
          <div style="width: 120px; background: #16A34A; color: #FFFFFF; font-family: 'Outfit', sans-serif; font-weight: 800; font-size: 12px; border-radius: 6px; display: flex; align-items: center; justify-content: center; letter-spacing: 0.5px;">
            4. EVIDENCE
          </div>
          <div class="bento-card" style="flex: 1; padding: 8px 12px; font-size: 11.2px; color: #334155; line-height: 1.35;">
            Generates timestamped spectrogram anomaly reports & SHA-256 tamper-proof logs. Mathematical vectors only — zero raw voice retention.
          </div>
        </div>
      </div>
      
      <!-- Telephony Degradation Showcase -->
      <div style="background: linear-gradient(135deg, #F0FDF4 0%, #DCFCE7 100%); border: 1.5px solid #22C55E; border-radius: 8px; padding: 12px 16px; flex: 1; display: flex; flex-direction: column; justify-content: space-around;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <strong style="color: #15803D; font-size: 13px; font-family: 'Outfit', sans-serif;">
            📡 Trained Against Simulated Indian Telephony — Not Studio Audio
          </strong>
          <span class="chip chip-green" style="font-size: 9px;">CORE DIFFERENTIATOR</span>
        </div>
        
        <div style="font-size: 11.5px; color: #1E293B; line-height: 1.4;">
          • <strong>Opus 8 kbps</strong> (WhatsApp / VoIP) · <strong>G.711 / AMR</strong> (PSTN & Bank Trunks) · <strong>5% Packet Loss</strong>.<br>
          • The micro-spectral clues that betray AI voices in studio benchmarks are stripped out by Indian mobile codecs.<br>
          • We augment all training data with our realistic channel degradation pipeline, forcing the model to learn codec-invariant acoustic invariants.
        </div>
      </div>
    </div>
  </div>
</div>

<!-- ====================================================
     SLIDE 4: Feasibility and Viability
     ==================================================== -->
<div class="slide-container" id="slide-4">
  <div class="tpl-oval">YOUR TEAM<br>LOGO</div>
  <div class="tpl-logo"></div>
  <div class="tpl-footer-bar">
    <span>@SIH Idea submission - Template</span>
    <span class="badge-footer">SLIDE 04</span>
  </div>
  
  <div class="slide-header-title">
    <span>FEASIBILITY AND VIABILITY</span>
    <span class="slide-header-tagline">— Backed by empirical pilot data and risk engineering</span>
  </div>
  
  <div class="content-area" style="display: flex; gap: 16px;">
    <!-- Left Column: Experiment & Budget -->
    <div style="width: 580px; display: flex; flex-direction: column; gap: 10px;">
      <div class="section-bar">Analysis of Feasibility (Pilot Experiment)</div>
      
      <!-- Modern Chart Bento Card -->
      <div class="bento-card" style="padding: 12px 16px; display: flex; flex-direction: column;">
        <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px;">
          <strong style="font-size: 12px; color: #1E3E62;">Empirical EER (Equal Error Rate — Lower is Better):</strong>
          <span class="chip chip-blue" style="font-size: 9.5px;">MEASURED PILOT</span>
        </div>
        
        <!-- Graphic Bars -->
        <div style="display: flex; align-items: flex-end; justify-content: center; gap: 50px; height: 80px; border-bottom: 2px solid #CBD5E1; padding-bottom: 6px; margin-top: 14px; margin-bottom: 4px;">
          <!-- Bar 1 -->
          <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 800; color: #0070C0;">7.9%</span>
            <div style="width: 76px; height: 35px; background: linear-gradient(180deg, #38BDF8 0%, #0070C0 100%); border-radius: 4px 4px 0 0; box-shadow: 0 2px 6px rgba(0, 112, 192, 0.25);"></div>
            <span style="font-size: 11px; font-weight: 700; color: #334155;">Clean Audio</span>
          </div>
          
          <!-- Bar 2 -->
          <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 800; color: #DC2626;">13.5%</span>
            <div style="width: 76px; height: 60px; background: linear-gradient(180deg, #F87171 0%, #DC2626 100%); border-radius: 4px 4px 0 0; box-shadow: 0 2px 6px rgba(220, 38, 38, 0.25);"></div>
            <span style="font-size: 11px; font-weight: 700; color: #334155;">+ Phone Line</span>
          </div>
          
          <!-- Bar 3 -->
          <div style="display: flex; flex-direction: column; align-items: center; gap: 4px;">
            <span style="font-family: 'JetBrains Mono', monospace; font-size: 13px; font-weight: 800; color: #16A34A;">11.7%</span>
            <div style="width: 76px; height: 50px; background: linear-gradient(180deg, #4ADE80 0%, #16A34A 100%); border-radius: 4px 4px 0 0; box-shadow: 0 2px 6px rgba(22, 163, 74, 0.25);"></div>
            <span style="font-size: 11px; font-weight: 700; color: #334155;">+ Enrolled Ref</span>
          </div>
        </div>
        
        <div style="font-size: 9.8px; color: #64748B; font-style: italic; line-height: 1.3; margin-top: 4px;">
          Our own pilot run (23 Aug 2026) · Strict leak-free protocol, speaker-disjoint fit/test split (n=119). Telephony degrades accuracy; enrolment fusion claws back ~30% of performance loss.
        </div>
      </div>
      
      <!-- Operations & Scope Card -->
      <div class="bento-card" style="padding: 10px 14px; font-size: 11.2px; line-height: 1.35; display: flex; flex-direction: column; gap: 4px;">
        <div><strong>Budget:</strong> ₹0–10,000 total. GPU compute free via IndiaAI Mission & Kaggle (30h/wk).</div>
        <div><strong>Hardware:</strong> Single 16 GB laptop. Full on-device execution guarantees offline demo uptime.</div>
        <div><strong>Timeline:</strong> Pipeline built (Sept) → Screening (Oct–Nov) → Finale 36h Sprint (Dec).</div>
        <div><strong>Scope Discipline:</strong> Core 4 layers fully built; remaining components strictly designed and labelled.</div>
      </div>
      
      <!-- Repository Proof Box -->
      <div style="background: #EFF6FF; border: 1.5px solid #0070C0; border-radius: 8px; padding: 9px 12px;">
        <div style="color: #0070C0; font-weight: 800; font-size: 11.5px; margin-bottom: 2px;">
          📦 Already Built — A Code Repository, Not Just A Plan
        </div>
        <div style="font-size: 10.5px; color: #334155; line-height: 1.35;">
          Leak-free evaluation harness · Telephony channel simulator (Opus/G.711/Packet Loss) · Enrolment fusion logic · Kaggle full-scale GPU batch scripts ready to run.
        </div>
      </div>
    </div>
    
    <!-- Right Column: Risk & Mitigation Table -->
    <div style="flex: 1; display: flex; flex-direction: column; gap: 10px;">
      <div class="section-bar">Potential Challenges, Risks & Mitigation Strategies</div>
      
      <div class="bento-card" style="flex: 1; padding: 6px 10px;">
        <table class="cmp-table" style="height: 100%;">
          <thead>
            <tr>
              <th style="background: #FEE2E2; color: #991B1B; width: 44%;">Identified Risk / Threat</th>
              <th style="background: #1E3E62; color: #FFFFFF; width: 56%;">Engineered Counter-Strategy</th>
            </tr>
          </thead>
          <tbody>
            <tr>
              <td style="background: #FEF2F2; color: #991B1B; font-weight: 600; border-left: 3px solid #EF4444;">
                Detectors blind to novel zero-day voice cloning tools
              </td>
              <td class="cmp-row-right">
                Enrolment-first matching verifies the known human, sidestepping tool detection.
              </td>
            </tr>
            <tr>
              <td style="background: #FEF2F2; color: #991B1B; font-weight: 600; border-left: 3px solid #EF4444;">
                Phone codecs strip micro-acoustic synthesis artifacts
              </td>
              <td class="cmp-row-right">
                Channel-hardened training across simulated Indian telephony conditions.
              </td>
            </tr>
            <tr>
              <td style="background: #FEF2F2; color: #991B1B; font-weight: 600; border-left: 3px solid #EF4444;">
                Naive always-on alarms produce 50 false alarms per attack
              </td>
              <td class="cmp-row-right">
                Semantic trigger restricts deep scoring to high-stakes transfer prompts.
              </td>
            </tr>
            <tr>
              <td style="background: #FEF2F2; color: #991B1B; font-weight: 600; border-left: 3px solid #EF4444;">
                Live human using RVC voice conversion beats liveness
              </td>
              <td class="cmp-row-right">
                Two-branch detection catches prosody & cadence mismatch of the human driver.
              </td>
            </tr>
            <tr>
              <td style="background: #FEF2F2; color: #991B1B; font-weight: 600; border-left: 3px solid #EF4444;">
                Public deepfake checkpoints suffer dataset contamination
              </td>
              <td class="cmp-row-right">
                Caught one public model scoring 0.0% fake; we enforce leak-free code assertions.
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </div>
  </div>
</div>

<!-- ====================================================
     SLIDE 5: Impact and Benefits
     ==================================================== -->
<div class="slide-container" id="slide-5">
  <div class="tpl-oval">YOUR TEAM<br>LOGO</div>
  <div class="tpl-logo"></div>
  <div class="tpl-footer-bar">
    <span>@SIH Idea submission - Template</span>
    <span class="badge-footer">SLIDE 05</span>
  </div>
  
  <div class="slide-header-title">
    <span>IMPACT AND BENEFITS</span>
    <span class="slide-header-tagline">— Protecting India's default communication channel</span>
  </div>
  
  <div class="content-area" style="display: flex; flex-direction: column; gap: 10px;">
    <!-- Section 1: Target Audiences -->
    <div class="section-bar">Potential Impact On The Target Audience</div>
    
    <div style="display: flex; gap: 14px;">
      <!-- Audience 1 -->
      <div class="bento-card" style="flex: 1; padding: 10px 14px; display: flex; flex-direction: column; gap: 6px; border-top: 3px solid #0070C0;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <strong style="color: #0070C0; font-size: 13px; font-family: 'Outfit', sans-serif;">Individuals & Families</strong>
          <span class="chip chip-blue" style="font-size: 9px;">CITIZEN SAFETY</span>
        </div>
        <div style="font-size: 11px; line-height: 1.35;">
          <div style="color: #DC2626; font-weight: 700; margin-bottom: 2px;">THE ATTACK:</div>
          "Mum, I've had an accident, wire ₹50,000 now." Cloned-relative extortion calls target vulnerable parents.
        </div>
        <div style="font-size: 11px; line-height: 1.35; border-top: 1px dashed #E2E8F0; padding-top: 4px;">
          <div style="color: #16A34A; font-weight: 700; margin-bottom: 2px;">OUR SOLUTION:</div>
          Enrolled family voice profiles on personal device; generates warnings in regional Indian languages.
        </div>
      </div>
      
      <!-- Audience 2 -->
      <div class="bento-card" style="flex: 1; padding: 10px 14px; display: flex; flex-direction: column; gap: 6px; border-top: 3px solid #1F497D;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <strong style="color: #1F497D; font-size: 13px; font-family: 'Outfit', sans-serif;">Banks & Enterprises</strong>
          <span class="chip chip-navy" style="font-size: 9px;">COMMERCIAL TRUNKS</span>
        </div>
        <div style="font-size: 11px; line-height: 1.35;">
          <div style="color: #DC2626; font-weight: 700; margin-bottom: 2px;">THE ATTACK:</div>
          CXO impersonation on ₹2 crore fund-transfer approvals. 30s of conference audio suffices for a clone.
        </div>
        <div style="font-size: 11px; line-height: 1.35; border-top: 1px dashed #E2E8F0; padding-top: 4px;">
          <div style="color: #16A34A; font-weight: 700; margin-bottom: 2px;">OUR SOLUTION:</div>
          Verification activates exactly on the transfer prompt, requiring secondary authorization before release.
        </div>
      </div>
      
      <!-- Audience 3 -->
      <div class="bento-card" style="flex: 1; padding: 10px 14px; display: flex; flex-direction: column; gap: 6px; border-top: 3px solid #16A34A;">
        <div style="display: flex; align-items: center; justify-content: space-between;">
          <strong style="color: #16A34A; font-size: 13px; font-family: 'Outfit', sans-serif;">Telecom & Government</strong>
          <span class="chip chip-green" style="font-size: 9px;">NATIONAL INFRA</span>
        </div>
        <div style="font-size: 11px; line-height: 1.35;">
          <div style="color: #DC2626; font-weight: 700; margin-bottom: 2px;">THE ATTACK:</div>
          Zero centralized defense layer across carrier networks; institutions operate isolated blind defenses.
        </div>
        <div style="font-size: 11px; line-height: 1.35; border-top: 1px dashed #E2E8F0; padding-top: 4px;">
          <div style="color: #16A34A; font-weight: 700; margin-bottom: 2px;">OUR SOLUTION:</div>
          Standardized drop-in voice-integrity API & SDK for carrier trunks — directly fulfilling the PS vision.
        </div>
      </div>
    </div>
    
    <!-- Section 2: 4 Pillars of Value -->
    <div class="section-bar">Comprehensive Benefits (Social, Economic, Operational, Environmental)</div>
    
    <div style="display: flex; gap: 12px;">
      <div class="bento-card" style="flex: 1; padding: 9px 12px; background: #F8FAFC;">
        <div class="chip chip-blue" style="margin-bottom: 4px;">SOCIAL</div>
        <div style="font-size: 11.5px; font-weight: 700; color: #1E3E62; margin-bottom: 2px;">Restores Voice Trust</div>
        <div style="font-size: 10.5px; color: #64748B; line-height: 1.3;">
          Voice is India's default civic & banking channel. We protect citizens with the fewest digital alternatives.
        </div>
      </div>
      
      <div class="bento-card" style="flex: 1; padding: 9px 12px; background: #F8FAFC;">
        <div class="chip chip-navy" style="margin-bottom: 4px;">ECONOMIC</div>
        <div style="font-size: 11.5px; font-weight: 700; color: #1E3E62; margin-bottom: 2px;">Cuts Impersonation Losses</div>
        <div style="font-size: 10.5px; color: #64748B; line-height: 1.3;">
          AI voice fraud is up 148%/yr. Intervening at the wire transfer prompt ensures money never leaves.
        </div>
      </div>
      
      <div class="bento-card" style="flex: 1; padding: 9px 12px; background: #F8FAFC;">
        <div class="chip chip-amber" style="margin-bottom: 4px;">OPERATIONAL</div>
        <div style="font-size: 11.5px; font-weight: 700; color: #1E3E62; margin-bottom: 2px;">Survives In Production</div>
        <div style="font-size: 10.5px; color: #64748B; line-height: 1.3;">
          99% detectors fail via 50:1 false alarms. Triggering on stakes ensures staff never disable the security gate.
        </div>
      </div>
      
      <div class="bento-card" style="flex: 1; padding: 9px 12px; background: #F8FAFC;">
        <div class="chip chip-green" style="margin-bottom: 4px;">ENVIRONMENTAL</div>
        <div style="font-size: 11.5px; font-weight: 700; color: #1E3E62; margin-bottom: 2px;">Zero Always-On Cloud</div>
        <div style="font-size: 10.5px; color: #64748B; line-height: 1.3;">
          Edge execution avoids streaming millions of calls to cloud datacentres, reducing carbon & compute footprint.
        </div>
      </div>
    </div>
    
    <!-- Closing Banner Strip -->
    <div style="background: linear-gradient(135deg, #1F497D 0%, #0F172A 100%); border-radius: 8px; padding: 11px 20px; text-align: center; color: #FFFFFF; font-family: 'Outfit', sans-serif; font-size: 13.5px; font-weight: 700; box-shadow: 0 4px 14px rgba(15, 23, 42, 0.2); letter-spacing: 0.2px;">
      "Our accuracy number is not the product. The architecture around the number is the product — because a 95% detector deployed naively produces 98% false alerts."
    </div>
  </div>
</div>

<!-- ====================================================
     SLIDE 6: Research and References
     ==================================================== -->
<div class="slide-container" id="slide-6">
  <div class="tpl-oval">YOUR TEAM<br>LOGO</div>
  <div class="tpl-logo"></div>
  <div class="tpl-footer-bar">
    <span>@SIH Idea submission - Template</span>
    <span class="badge-footer">SLIDE 06</span>
  </div>
  
  <div class="slide-header-title">
    <span>RESEARCH AND REFERENCES</span>
    <span class="slide-header-tagline">— Literature-grounded citations and reproducible experiments</span>
  </div>
  
  <div class="content-area" style="display: flex; flex-direction: column; gap: 8px;">
    <div class="section-bar">Details & Academic Citations Grounding Our Architecture</div>
    
    <div style="font-size: 11.5px; color: #1E3E62; font-style: italic;">
      Every design decision traces directly to published literature or our measured code. Numbers quoted reflect audited benchmarks:
    </div>
    
    <!-- 8 Citations Grid -->
    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 8px; flex: 1;">
      <div class="bento-card" style="padding: 8px 12px; font-size: 11px; line-height: 1.35;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
          <strong style="color: #1F497D; font-size: 12px;">ASVspoof 5 Challenge</strong>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #0284C7;">asvspoof.org</span>
        </div>
        SOTA anti-spoofing benchmark. Best systems achieve 9–20% EER on real audio — why claiming 99% accuracy is scientifically invalid.
      </div>
      
      <div class="bento-card" style="padding: 8px 12px; font-size: 11px; line-height: 1.35;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
          <strong style="color: #1F497D; font-size: 12px;">Base-Rate Fallacy in Intrusion Detection</strong>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #0284C7;">arxiv:2203.08801</span>
        </div>
        Explains mathematically why 99% detectors drown operators in 50:1 false alarms on rare attacks — our rationale for trigger layers.
      </div>
      
      <div class="bento-card" style="padding: 8px 12px; font-size: 11px; line-height: 1.35;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
          <strong style="color: #1F497D; font-size: 12px;">SASV Challenge (Speaker Verification)</strong>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #0284C7;">Interspeech</span>
        </div>
        The fusion research our enrolment-first pipeline builds upon: combining countermeasure scores with speaker verification embeddings.
      </div>
      
      <div class="bento-card" style="padding: 8px 12px; font-size: 11px; line-height: 1.35;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
          <strong style="color: #1F497D; font-size: 12px;">"The Watermark Shortcut"</strong>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #0284C7;">arxiv:2606.23335</span>
        </div>
        Shows detectors memorize generator watermarks instead of synthetic artifacts, failing on unwatermarked audio. A flaw we audit for.
      </div>
      
      <div class="bento-card" style="padding: 8px 12px; font-size: 11px; line-height: 1.35;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
          <strong style="color: #1F497D; font-size: 12px;">RawBoost (Tak et al., ICASSP 2022)</strong>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #0284C7;">IEEE ICASSP</span>
        </div>
        Telephony-robust data augmentation foundation. The algorithmic basis for our codec + packet-loss degradation simulator.
      </div>
      
      <div class="bento-card" style="padding: 8px 12px; font-size: 11px; line-height: 1.35;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
          <strong style="color: #1F497D; font-size: 12px;">IndicSynth Multilingual Dataset</strong>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #0284C7;">AI4Bharat</span>
        </div>
        Indian-language synthetic speech corpus covering diverse regional dialects — our roadmap for testing beyond English benchmarks.
      </div>
      
      <div class="bento-card" style="padding: 8px 12px; font-size: 11px; line-height: 1.35;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
          <strong style="color: #1F497D; font-size: 12px;">ASVspoof 2019 Logical Access Dataset</strong>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #0284C7;">Edinburgh DataShare</span>
        </div>
        Speaker-paired genuine and spoofed speech samples that powered our preliminary leak-free enrolment fusion pilot.
      </div>
      
      <div class="bento-card" style="padding: 8px 12px; font-size: 11px; line-height: 1.35;">
        <div style="display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 2px;">
          <strong style="color: #1F497D; font-size: 12px;">Independent Commercial Testing</strong>
          <span style="font-family: 'JetBrains Mono', monospace; font-size: 10px; color: #0284C7;">Third-Party Audit</span>
        </div>
        Vendors advertise 99% self-reported accuracy; independent field audits measure real-world performance at 60–75% over live VoIP.
      </div>
    </div>
    
    <!-- Verified Own Work Banner -->
    <div style="background: #F0FDF4; border: 1.5px solid #16A34A; border-radius: 8px; padding: 10px 14px; display: flex; align-items: center; justify-content: space-between;">
      <div style="font-size: 11.2px; color: #1E293B; line-height: 1.35;">
        <strong style="color: #15803D;">🧪 Our Own Work:</strong>
        Leak-free probe methodology (task-naive backbone, speaker-disjoint fit/test split asserted in code) · Telephony channel simulator (Opus/G.711/Packet Loss) · End-to-end reproducible experiment harness in Python.
      </div>
      <span class="chip chip-green" style="font-size: 9.5px; flex-shrink: 0; margin-left: 12px;">100% REPRODUCIBLE</span>
    </div>
  </div>
</div>

</body>
</html>
"""

async def main():
    os.makedirs("ppt-preview", exist_ok=True)
    html_path = os.path.abspath("ppt-preview/index.html")
    with open(html_path, "w", encoding="utf-8") as f:
        f.write(HTML_CONTENT)
    print(f"Wrote updated HTML preview to {html_path}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch()
        page = await browser.new_page(viewport={"width": 1600, "height": 1000})
        await page.goto(f"file://{html_path}")
        await page.wait_for_timeout(1500)
        
        for i in range(1, 7):
            slide_elem = page.locator(f"#slide-{i}")
            out_img = f"ppt-preview/slide-{i:02d}.png"
            await slide_elem.screenshot(path=out_img)
            print(f"Captured {out_img}")
            
        await browser.close()
        print("All preview screenshots updated successfully!")

if __name__ == "__main__":
    asyncio.run(main())
