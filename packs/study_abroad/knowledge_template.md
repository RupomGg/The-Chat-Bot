# {{Consultancy name}}
Established {{year}}. Counsellor hotline: {{phone}} (Sat–Thu 10:00–19:00). Facebook: {{url}}. Website: {{url}}

## Branches and hours
- Dhaka (Banani): {{address}}, maps {{link}}. Sat–Thu 10:00–19:00.
- Online counselling: Google Meet, Sat–Thu 11:00–20:00.

## Our services and fees
- Counselling: free.
- Application processing: ৳{{x}} per application / package {{...}}. Refund policy: {{...}}
- Visa file preparation: ৳{{x}}. Not included: university fees, visa fees, IHS, flights.
- We do not guarantee admission or visa.

## Destinations
### United Kingdom
- Levels: Foundation, Bachelor, Masters. Intakes: January, May, September.
- English: IELTS UKVI/Academic usually 6.0 overall (no band < 5.5) for Bachelor; 6.5 (5.5/6.0) for Masters. MOI accepted by: {{list or "none of our partners currently"}}.
- Study gap: {{consultancy's stated position}}.
- Tuition range with our partners: £{{x}}–£{{y}}/year. Living: London £{{x}}/month, outside £{{y}}/month (UKVI figures).
- Funds/solvency: first-year tuition balance + living costs, held 28 days. {{consultancy guidance}}
- Work: 20 h/week in term time. Dependants: {{current rule as stated by consultancy}}.
- Notes: several UK universities currently restrict Bangladeshi applicants; a counsellor confirms current options.
### Malaysia
...
### Hungary / Finland / Cyprus / Australia / Canada
...

## Partner universities
| University | Country | Levels | Tuition/yr | English min | Alt. tests | Intakes | Scholarship |
|---|---|---|---|---|---|---|---|

## Scholarships we can help with
- {{name}}: eligibility, amount, deadline.

## Process
1. Free counselling → 2. Shortlist → 3. Applications → 4. Offer → 5. Deposit/CAS/COE → 6. Visa file → 7. Pre-departure.

## Documents to bring to counselling
SSC/HSC/Bachelor certificates and transcripts, English test result (if any), passport (bring, don't send), CV if working, sponsor details.

## Events
- {{date}}: {{title}} at {{branch}}. Free registration.

## Handoff rules
- Previous visa refusal → counsellor.
- Masters with CGPA below {{x}} → counsellor.
- Any fee negotiation or refund → counsellor.

## Never say
- Visa success rates or guarantees. Any discount not listed here.

## Quick answers
<!-- Parsed at publish time into buttons + exact-match lookups (PRD §6.8). No AI is used for these. -->
### FEES_OURS
triggers: fees, service charge, apnader fee koto, খরচ কত
buttons: BOOK, COUNTRIES
answer_bn: আমাদের কাউন্সেলিং সম্পূর্ণ ফ্রি। আবেদন প্রসেসিং ফি ৳{{x}} ...
answer_en: Counselling is free. Application processing is ৳{{x}} ...
### OFFICE
triggers: address, office kothay, ঠিকানা, location
answer_bn: ...
answer_en: ...
### BOOK
triggers: book, counselling, appointment
action: start_booking        # hands over to the booking flow (model call)
