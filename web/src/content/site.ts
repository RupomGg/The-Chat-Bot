// Every visible string on the site. Copy rules: design/LANDING_GUIDE.md §7.
export const WHATSAPP = "8801966163995";
// Chat backend, e.g. "https://app.halcyo.tech". Empty = no live widget, "Try it" hidden.
export const WIDGET_ORIGIN = "";

export const wa = (text: string) => `https://wa.me/${WHATSAPP}?text=${encodeURIComponent(text)}`;
export const BOOK = wa("Hi, I saw Halcyo and want a demo.");

export const HERO_IMAGE = "https://lh3.googleusercontent.com/aida/AEtjO1WXFBuhB21ru-1KY6ca7WHd5X1VpeWW4eOZrcQ-GIC6SRhaVQ_b4ZJ6rIeufXZO1QnkA5jP9KP4O-PW6I0Z5z2uOR51HN-pI2qA34qFmGjE3fcvH0ALEgw4U5F7x4GvkuVqPrNR6f_M3bBFHjVwlDOYUeyoJQ8u0Qr5Fi4B4bCGlLJZws4hYRrLGSeVwe6Qvz5O5fLB_0z7irJIotAIUovK2V1OoGSTjmMJhJ2kBYdTixqy_U6MwjyjnNrH";

export type Chat = {
  tab: string; biz: string; lang: string;
  c1: string; b1: string; chips: string[]; pick: number; done: string;
  asks: string[]; does: string; never: string;
};

export const chats: Chat[] = [
  {
    tab: "Study abroad", biz: "Bright Path Consultancy", lang: "bn-Latn",
    c1: "UK te IELTS 6 hole hobe? Total koto lagbe?",
    b1: "IELTS 6.0 (kono band 5.5 er niche na) hole amader partner university te Bachelor e apply kora jay. Total khoroch city ar university r upor depend kore, counsellor apnake exact hishab diye dibe. Free counselling book korbo?",
    chips: ["Kal 11 am", "Kal 4 pm", "Online"], pick: 0, done: "Done! Kal 11 am e counselling, Banani office.",
    asks: ["UK te IELTS 6 hole hobe?", "January intake e ekhono apply kora jabe?", "Bank solvency koto lakh dekhano lagbe?"],
    does: "Answers from your fees and rules, collects results, IELTS score, study gap, budget and intake, then books the counselling session.",
    never: "Visa guarantees or visa odds. Visa cases go straight to your counsellor.",
  },
  {
    tab: "Pet care", biz: "Paws & Care Dhanmondi", lang: "bn-Latn",
    c1: "Persian cat er grooming koto? Kal sokale slot ache?",
    b1: "Persian cat er full grooming ৳1,500. Kal sokale 10, 11 ar 12 tay slot khali ache. Konta book korbo?",
    chips: ["10 am", "11 am", "12 pm"], pick: 1, done: "Booked! Kal 11 am, grooming.",
    asks: ["Bilai bath ar hair cut package koto?", "Rabies vaccine ar deworming ache?", "Friday te slot faka ache?"],
    does: "Explains your packages and prices, asks pet type, breed, age and vaccine history, and books a grooming slot or vet visit.",
    never: "Diagnosis or treatment. Urgent cases go straight to the vet's phone.",
  },
  {
    tab: "Clinics", biz: "Dr. Rahman's Chamber", lang: "bn",
    c1: "ডাক্তার রহমানের কালকের সিরিয়াল পাওয়া যাবে?",
    b1: "জি, কাল সন্ধ্যায় ৫টা, ৫:৩০ আর ৬টায় সিরিয়াল খালি আছে। ভিজিট ফি ৳৮০০। কোনটা নেবেন?",
    chips: ["৫টা", "৫:৩০", "৬টা"], pick: 1, done: "সিরিয়াল কনফার্ম: কাল ৫:৩০। পুরনো প্রেসক্রিপশন সাথে আনবেন।",
    asks: ["Doctor consultation fee koto?", "Test er age ki khali pete ashte hobe?", "Serial kivabe pabo?"],
    does: "Shares doctor days and fees, test preparation and branch address, and books the serial.",
    never: "Diagnosis, medicine names or doses, or reading lab reports. Emergencies go to your phone number and the nearest hospital.",
  },
  {
    tab: "Law firms", biz: "Haque & Associates", lang: "en",
    c1: "I have a land dispute. How much is a consultation?",
    b1: "A one-hour consultation is ৳2,000. A lawyer will look at your matter in person. When would you like to come in?",
    chips: ["Sun 3 pm", "Mon 11 am", "Tue 5 pm"], pick: 0, done: "Booked for Sunday, 3 pm. Please bring your land documents.",
    asks: ["Property dispute consult fee koto?", "Chamber er address ta diben?", "Online consultation hoy?"],
    does: "Explains consultation fees, collects the type of matter (no case details), and books a chamber or online meeting.",
    never: "Legal opinions or case outcomes.",
  },
];

export const problems = [
  { icon: "hourglass", title: "\"Typically replies within a day\"", text: "Customers don't wait a day. When they ask about fees or appointments, they message the next business." },
  { icon: "moon", title: "Messages arrive after hours", text: "Most messages come in the evening and on Fridays, when your staff is rightly resting." },
  { icon: "receipt", title: "Ads without answers", text: "You pay for Facebook ads, but can't see which ad brought which customer." },
];

export const steps = [
  ["Answers", "Your common questions, only from your own fees, timings and rules."],
  ["Learns", "What you need about each customer while chatting. Never a form."],
  ["Scores", "Each lead hot, warm or cold."],
  ["Books", "The appointment at your branch or online."],
  ["Alerts", "Your staff within 30 seconds when a hot lead or a booking comes in, with the chat summary and the ad it came from."],
  ["Hands over", "To a person when the customer asks, or when a question needs a professional."],
];

export const plans = [
  { name: "Starter", price: "৳12,000", pick: false, items: ["500 conversations a month", "Messenger and website", "3 staff seats", "Appointment booking"] },
  { name: "Growth", price: "৳25,000", pick: true, items: ["1,500 conversations a month", "Messenger, WhatsApp, Telegram, website", "10 staff seats", "Ad tracking, lead scoring and reports"] },
  { name: "Scale", price: "৳45,000", pick: false, items: ["4,000 conversations a month", "All channels, several branches", "Unlimited staff seats", "CRM link and priority support"] },
];

export const faqs = [
  ["Will it say wrong things about my fees or services?", "It answers only from your own knowledge file. If it doesn't know, it passes the chat to your staff. Every change is tested before it goes live."],
  ["Will it give medical or legal advice?", "No. It books appointments, answers questions about your business and hands anything professional to your team."],
  ["What about customer privacy?", "It never asks for passports, NID, bank statements or medical reports in chat. We follow the Bangladesh Personal Data Protection Act 2026."],
  ["Do I need my own Meta app or WhatsApp number?", "We set everything up in your own Business account. You keep ownership."],
  ["What happens when my staff replies?", "The bot pauses for that chat, so your customer talks to one person at a time."],
  ["My business isn't listed. Can I use it?", "If you sell a service and take bookings, it very likely fits. Book a demo and ask."],
];
