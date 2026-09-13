# Privacy

What happens to personal data around SDLCraft — information under Articles 13
and 14 GDPR. Nothing else about your projects ever leaves your machine.

**Responsible:** Andreas Pfrengle (Einzelunternehmer), Am Blasiwald 34, 79183 Waldkirch, Germany,
sdlc@agentmail.to

## When you buy

Polar Software Inc. sells SDLCraft as merchant of record and handles your
payment data under its own privacy notice — we never see your payment details.
From it we receive your **GitHub username**, your **e-mail address** and
whether your subscription is running, so that we can grant and revoke access to
the repository and reach you about your licence (Art. 6(1)(b) GDPR). We keep
that record for as long as tax and commercial law require (§§ 257 HGB, 147 AO).
GitHub necessarily sees that your account has access.

## Bug reports from the skills (off by default)

SDLCraft can tell us when one of its own skills misbehaves, so it gets fixed
for everyone. **It is off unless you turn it on** — `/sdlc:setup` asks once —
and `python .claude/sdlc/lessons.py consent --set off` turns it off again at
any time. The basis is your consent (Art. 6(1)(a) GDPR); withdrawing it changes
nothing about what was sent before.

A report says what the skill did wrong, which skill and version it was, and
numeric counts. File paths and e-mail addresses are stripped before sending,
and your project appears only as a random id. It never contains your source
code or your specifications. The receiving server sees the IP address the
report came from, which is not stored with it. Cloudflare, Inc. hosts that
endpoint as our processor, which can involve a transfer to the United States
under the Standard Contractual Clauses.

We keep reports until the defect is fixed and that version is out of support,
at most 24 months. Declining costs you nothing — everything works the same.

## The AI model you use

SDLCraft drives an AI model through your own account with its provider. What
you send them is between you and them; we receive nothing through it.

## Writing to us

If you e-mail us or open an issue, we use what you send to answer you
(Art. 6(1)(b) or (f) GDPR). Issues on GitHub are public.

## Your rights

You can ask us for a copy of your data, have it corrected or deleted, restrict
or object to its use, and receive it in a portable form (Art. 15–21 GDPR). You
can also complain to a data protection supervisory authority.
