"""
daily_forecast.py  ─ Hora Rashifal Engine v3
=============================================
Signal-based daily forecast engine with TRUE daily uniqueness.

v3 improvements (vs v2):
  - Tithi-based per-topic flavour (changes every ~24h)
  - Transiting Moon's nakshatra-based per-topic flavour (changes every ~24h)
  - Day-of-week rotation between Maha/Antardasha lord colouring
  - Daily-seed rotation for "quiet day" fallback messages
  - Natal nakshatra line rotates on/off every other day
  - Moon degree-of-sign "intensity" modifier (early/middle/late)

Architecture:
  SIGNALS[(planet, house_from_moon)] -> {topic: (weight, text)}
  Each topic collects ALL matching signals for today's transits,
  combines positives + negatives, layers in daily-changing flavour
  (tithi, transit Moon nakshatra, dasha lord, moon degree zone),
  and produces a final paragraph that is materially different every day.

Topics:
  family | married_life | love | health | education |
  business | job | finances | arts | sports | politics

Usage:
    from services.daily_forecast import generate_daily_forecast
    msgs = generate_daily_forecast(kundli_result, name="Deepak", gender="Male")
"""

from __future__ import annotations
from datetime import datetime, timezone
import os
import swisseph as swe

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
swe.set_ephe_path(BASE_DIR)

from utils.config import signs, nakshatras

# ─────────────────────────────────────────────────────────────────────────────
# Reference tables
# ─────────────────────────────────────────────────────────────────────────────

SIGN_INDEX = {s: i for i, s in enumerate(signs)}

PLANET_ICONS = {
    "Sun": "☀️", "Moon": "🌙", "Mars": "🔴", "Mercury": "💚",
    "Jupiter": "🟡", "Venus": "⚪", "Saturn": "🪐",
    "Rahu": "🐉", "Ketu": "☄️",
}

WEEKDAY_LORDS = {
    "Sunday": "Sun", "Monday": "Moon", "Tuesday": "Mars",
    "Wednesday": "Mercury", "Thursday": "Jupiter",
    "Friday": "Venus", "Saturday": "Saturn",
}

EXALTED = {
    "Sun": "Aries", "Moon": "Taurus", "Mars": "Capricorn",
    "Mercury": "Virgo", "Jupiter": "Cancer",
    "Venus": "Pisces", "Saturn": "Libra",
}
DEBILITATED = {
    "Sun": "Libra", "Moon": "Scorpio", "Mars": "Cancer",
    "Mercury": "Pisces", "Jupiter": "Capricorn",
    "Venus": "Virgo", "Saturn": "Aries",
}
OWN_SIGNS = {
    "Sun": {"Leo"}, "Moon": {"Cancer"},
    "Mars": {"Aries", "Scorpio"}, "Mercury": {"Gemini", "Virgo"},
    "Jupiter": {"Sagittarius", "Pisces"},
    "Venus": {"Taurus", "Libra"}, "Saturn": {"Capricorn", "Aquarius"},
}

TITHI_NAMES = [
    "Pratipada", "Dwitiya", "Tritiya", "Chaturthi", "Panchami",
    "Shashthi", "Saptami", "Ashtami", "Navami", "Dashami",
    "Ekadashi", "Dwadashi", "Trayodashi", "Chaturdashi", "Purnima",
]

# ─────────────────────────────────────────────────────────────────────────────
# THE SIGNAL TABLE
# (planet, house_from_moon) -> {topic: (weight, text)}
# weight: +2 very good  +1 good  -1 caution  -2 bad
# ─────────────────────────────────────────────────────────────────────────────

SIGNALS: dict[tuple[str, int], dict[str, tuple[int, str]]] = {

    # ══════════ SUN ══════════
    ("Sun", 1): {
        "health":  (-1, "Sun in Janma Rashi drains vitality today — rest more, avoid overexertion."),
        "job":     (-1, "Superiors may be critical; keep a low profile at work today."),
        "family":  (-1, "A domineering attitude at home can stir friction — soften your tone with family."),
    },
    ("Sun", 2): {
        "finances": (-1, "Expenditure rises today; avoid impulsive purchases or taking loans."),
        "family":   (-1, "Harsh words at the dining table can create lasting resentment — speak gently."),
        "health":   (-1, "Eye and throat discomfort is possible — stay well hydrated today."),
    },
    ("Sun", 3): {
        "job":       (2, "Sun in the 3rd gives bold initiative — excellent for presentations, cold calls, and leadership tasks."),
        "education": (1, "Sharp mental energy supports competitive exams and self-study today."),
        "sports":    (2, "Courage and stamina are at their peak — compete with full confidence today."),
    },
    ("Sun", 4): {
        "family": (-1, "Sun in the 4th can create ego clashes with parents or authority figures at home."),
        "health": (-1, "Heart and chest sensitivity possible — avoid very spicy or heavy food today."),
        "job":    (-1, "Domestic stress may distract from work — resolve home matters first."),
    },
    ("Sun", 5): {
        "education": (2, "Sun illuminates the 5th — excellent for creative learning, competitive exams, and academic performance."),
        "love":      (1, "Confidence and charisma are high — your personality shines in romantic situations today."),
        "arts":      (2, "Creative and artistic expression is powerfully supported. Take centre stage."),
    },
    ("Sun", 6): {
        "health":   (2, "Sun in the 6th destroys illness — immunity is strong, energy is high today."),
        "job":      (2, "Enemies and competitors are subdued. Great day to tackle difficult tasks or rivals at work."),
        "politics": (2, "You gain the upper hand over opponents; public positioning is very favourable today."),
    },
    ("Sun", 7): {
        "married_life": (-1, "Sun in the 7th can inflate the ego in partnership — avoid being domineering with your spouse."),
        "love":         (-1, "Power dynamics may create friction in romance — practise humility today."),
        "job":          (1, "Client-facing and partnership work is energised; sign deals today."),
    },
    ("Sun", 8): {
        "health":   (-2, "Sun in the 8th weakens vitality and raises risk of hidden ailments — get adequate rest."),
        "finances": (-2, "Sudden financial loss or unexpected expenditure possible — avoid speculation today."),
        "job":      (-1, "Workplace politics may be intense today — avoid confrontation with seniors."),
    },
    ("Sun", 9): {
        "education": (2, "Sun in the 9th blesses higher learning — mentors, teachers, and guides are very supportive."),
        "family":    (1, "Father or paternal elders bring good news or blessings today."),
        "politics":  (2, "Fortune and divine grace support your public endeavours. A great day for bold positions."),
    },
    ("Sun", 10): {
        "job":      (2, "Sun at the career peak — bosses notice your work, recognition is imminent. Excel today."),
        "politics": (2, "Public image soars. Supporters rally around you; status and authority increase."),
        "business": (2, "Leadership and authority in business dealings are strongly supported — command the room."),
    },
    ("Sun", 11): {
        "finances": (2, "Sun in the 11th — income and gains are highlighted. Financial targets are likely to be met."),
        "job":      (2, "Excellent for networking, salary discussions, and achieving professional goals today."),
        "politics": (1, "Social influence is strong — your voice carries weight in groups and organisations."),
    },
    ("Sun", 12): {
        "finances": (-2, "Sun in the 12th increases hidden expenditure — monitor spending carefully today."),
        "health":   (-1, "Sleep disturbances and low immunity possible — prioritise rest today."),
        "job":      (-1, "Work behind the scenes rather than seeking the spotlight today."),
    },

    # ══════════ MOON ══════════
    ("Moon", 1): {
        "health": (-2, "Moon in Janma Rashi — the weakest day for body and mind. Rest, eat light, avoid all stress."),
        "family": (-1, "Emotional sensitivity is very high — small things may feel overwhelming at home today."),
        "love":   (-1, "You may feel clingy or insecure in relationships today — ground yourself before reaching out."),
    },
    ("Moon", 2): {
        "family":   (-1, "Moon in the 2nd with Rahu nearby creates a Grahan-like effect — beware of misunderstandings."),
        "finances": (-1, "Emotional spending is likely today — avoid shopping when you're feeling low."),
        "health":   (-1, "Dietary irregularities may cause digestive discomfort today."),
    },
    ("Moon", 3): {
        "family":    (2, "Moon in the 3rd creates a light, communicative atmosphere at home. Great day for family conversations."),
        "education": (1, "Short-distance travel and communication-based learning are highly favoured."),
        "love":      (1, "Flirtatious, witty energy today — light and fun romantic interactions flow easily."),
    },
    ("Moon", 4): {
        "family":    (-1, "Moon in the 4th stirs deep emotions at home — mother or maternal figures may need attention."),
        "health":    (-1, "Emotional restlessness may disturb sleep — practise calming routines tonight."),
        "education": (-1, "Difficulty concentrating today — study in short, focused blocks rather than long sessions."),
    },
    ("Moon", 5): {
        "love":      (2, "Moon in the 5th opens the heart fully — romantic feelings are intense, beautiful, and sincere."),
        "education": (2, "Intuition and memory are sharp today — excellent for studying creative or conceptual subjects."),
        "arts":      (2, "Emotional creativity peaks today; art, writing, and performance will flow naturally and powerfully."),
    },
    ("Moon", 6): {
        "health":   (2, "Moon in the 6th boosts immune system and fighting energy — great day for health routines."),
        "job":      (2, "Work efficiency is high; rivals are manageable. Push through your to-do list with confidence."),
        "finances": (1, "Day-to-day financial management is smooth; small wins and savings add up today."),
    },
    ("Moon", 7): {
        "married_life": (1, "Moon in the 7th heightens emotional intimacy — a tender, communicative day with your spouse."),
        "love":         (2, "You are deeply drawn to connecting with others — an ideal day for romantic conversations."),
        "business":     (1, "Partnership deals and client meetings carry good emotional momentum today."),
    },
    ("Moon", 8): {
        "health":   (-2, "Moon in the 8th brings hidden health vulnerabilities — avoid overexertion and toxic environments."),
        "finances": (-2, "Unexpected monetary shocks possible — hold off on major financial decisions today."),
        "family":   (-1, "Secretive family tensions or old wounds may resurface — handle with sensitivity."),
    },
    ("Moon", 9): {
        "education": (2, "Moon in the 9th brings a thirst for wisdom — excellent for higher education and spiritual learning."),
        "family":    (2, "Blessings from elders and a peaceful atmosphere at home. Good news from father is likely."),
        "love":      (1, "Spiritual and meaningful connections are favoured — depth over superficiality today."),
    },
    ("Moon", 10): {
        "job":      (2, "Moon at the career pinnacle — public recognition and emotional fulfilment in work. Great day to be visible."),
        "politics": (2, "Public approval is very high today. People respond warmly to your leadership."),
        "business": (2, "Your reputation and credibility carry the day — clients and partners trust you completely."),
    },
    ("Moon", 11): {
        "finances": (2, "Moon in the 11th — the best position for gains. Income, gifts, and wish-fulfilment are strongly indicated."),
        "family":   (2, "Joyful family interactions, good news, and social celebrations are likely today."),
        "love":     (1, "Social magnetism is high — you draw people toward you effortlessly today."),
    },
    ("Moon", 12): {
        "health":    (-1, "Moon in the 12th causes emotional drain — protect your mental health; limit screen time."),
        "finances":  (-1, "Hidden expenditure and wasteful spending can creep up — review your accounts today."),
        "education": (-1, "A reflective, inward day — better for revision and meditation than active new learning."),
    },

    # ══════════ MARS ══════════
    ("Mars", 1): {
        "health": (-1, "Mars in the 1st can raise blood pressure and cause headaches — avoid aggression today."),
        "family": (-2, "Short temper at home is a serious risk today — count to ten before responding to anyone."),
        "love":   (-1, "Impulsive romantic behaviour can create unnecessary drama — channel Mars into passion, not anger."),
    },
    ("Mars", 2): {
        "finances": (-2, "Mars in the 2nd is the classic impulsive-spending placement — avoid all major purchases today."),
        "family":   (-2, "Harsh words at home can cause lasting damage — Mars cuts like a blade in the 2nd house."),
        "health":   (-1, "Mouth, teeth, and throat may need attention — avoid very spicy or hot food."),
    },
    ("Mars", 3): {
        "job":       (2, "Mars in the 3rd gives laser focus, boldness, and the ability to push through all obstacles at work."),
        "sports":    (2, "Physical energy is exceptional today — compete aggressively. Victory is within reach."),
        "education": (1, "Strong mental drive supports technical and competitive subjects today."),
    },
    ("Mars", 4): {
        "family": (-2, "Mars in the 4th — the most combustible position for domestic peace. Avoid heated arguments at home."),
        "health": (-1, "Chest and respiratory sensitivity possible — avoid strenuous indoor exercise."),
        "job":    (-1, "Distraction from home stress may affect your work performance today."),
    },
    ("Mars", 5): {
        "love":      (1, "Mars in the 5th adds fire and passion to romance — intense, exciting, and deeply felt."),
        "education": (1, "Competitive drive is very high today — good for exam preparation and challenging subjects."),
        "arts":      (1, "Bold, dramatic artistic expression is favoured — don't hold back creatively today."),
    },
    ("Mars", 6): {
        "health":   (2, "Mars in the 6th is excellent — strong immunity, high stamina, enemies defeated today."),
        "job":      (2, "Outstanding drive to complete targets. Rivals and workplace obstacles are overcome with ease."),
        "sports":   (2, "Peak competitive energy today — train hard, compete boldly, perform at your very best."),
    },
    ("Mars", 7): {
        "married_life": (-2, "Mars in the 7th is a classic conflict indicator with spouse — avoid picking battles today."),
        "love":         (-1, "Passion can turn to possessiveness today — balance intensity with patience."),
        "business":     (-1, "Disagreements with partners or clients possible — keep negotiations calm."),
    },
    ("Mars", 8): {
        "health":   (-2, "Mars in the 8th — risk of accidents, injuries, or surgical issues. Be very careful physically today."),
        "finances": (-2, "Sudden financial disruption or hidden losses possible — avoid all risky investments."),
        "job":      (-1, "Intense, pressurised work environment today — stay calm under fire."),
    },
    ("Mars", 9): {
        "education": (1, "Drive to pursue higher learning is strong — good for research and advanced study today."),
        "sports":    (1, "Stamina and competitive spirit are elevated. Long-distance or endurance activities benefit."),
        "family":    (1, "Father or elder figures benefit from your protective, energetic support today."),
    },
    ("Mars", 10): {
        "job":      (2, "Mars in the 10th is a powerhouse for career — you act decisively, command attention, and deliver results."),
        "business": (2, "Aggressive business moves pay off today. Close deals, launch initiatives, lead from the front."),
        "politics": (1, "Fighting spirit wins the day in public life — you are seen as strong and capable."),
    },
    ("Mars", 11): {
        "finances": (2, "Mars in the 11th drives income and recovery of dues — chase pending payments aggressively today."),
        "job":      (2, "Goal-achievement energy is very high. You will push through limits to reach targets today."),
        "sports":   (2, "Competitive excellence peaks — go for the record, the title, the medal today."),
    },
    ("Mars", 12): {
        "health":   (-2, "Mars in the 12th can cause unseen health issues — hospitalisation risk; do not ignore any symptoms."),
        "finances": (-2, "Mars drains the 12th house of money through hidden channels — audit your expenses carefully."),
        "love":     (-1, "Secret romantic attraction is possible but may come with complications — proceed thoughtfully."),
    },

    # ══════════ MERCURY ══════════
    ("Mercury", 1): {
        "education": (2, "Mercury in your sign sharpens intelligence and communication — a brilliant day for all mental work."),
        "business":  (2, "Your negotiation skills are razor-sharp — the best day for contracts and clever deals."),
        "love":      (1, "Witty, expressive charm makes you irresistible today — words are your best romantic tool."),
    },
    ("Mercury", 2): {
        "finances":  (1, "Careful financial analysis and smart budgeting are strongly supported today."),
        "family":    (1, "Articulate, thoughtful communication brings harmony to family discussions."),
        "education": (1, "Memory retention and verbal skills are above average today — good for language learning."),
    },
    ("Mercury", 3): {
        "education": (2, "Mercury in the 3rd is its most powerful house — academic brilliance and excellent exams today."),
        "business":  (2, "Networking, outreach, and communication-heavy business tasks yield excellent results."),
        "job":       (2, "Written communication, emails, and presentations are impressive — speak up in all meetings."),
    },
    ("Mercury", 4): {
        "family":    (1, "Thoughtful communication at home prevents misunderstandings — a good day for family meetings."),
        "education": (1, "Home-based learning or online study is favoured today."),
        "finances":  (1, "Real estate or property-related paperwork can be handled smoothly today."),
    },
    ("Mercury", 5): {
        "education": (2, "Excellent for creative intelligence — writing, problem-solving, and academic competitions shine."),
        "love":      (2, "Playful, witty romantic energy — charm your partner with intelligent conversation and humour."),
        "arts":      (2, "Mercury in the 5th is ideal for creative writing, poetry, scriptwriting, and storytelling."),
    },
    ("Mercury", 6): {
        "job":       (1, "Analytical skills help you solve workplace problems efficiently and cleverly today."),
        "health":    (1, "Mercury supports medical analysis, health research, and communication with doctors today."),
        "education": (1, "Detail-oriented subjects and analytical problems are handled with exceptional clarity."),
    },
    ("Mercury", 7): {
        "business":     (2, "Partnership contracts and legal agreements are favoured — sign with confidence today."),
        "married_life": (1, "Open, intelligent communication with your spouse brings clarity and closeness today."),
        "love":         (1, "Intellectual connection with your partner deepens — great conversations lead to warmth."),
    },
    ("Mercury", 8): {
        "finances":  (-1, "Mercury in the 8th can cause confusion in financial matters — read all fine print carefully."),
        "health":    (-1, "Nervous system sensitivity possible — avoid overstimulation and excessive screen time."),
        "education": (-1, "Scattered thinking may hinder study — use structured notes and short study sessions today."),
    },
    ("Mercury", 9): {
        "education": (2, "Mercury in the 9th — the best placement for higher education, research, and publishing today."),
        "job":       (1, "Legal, publishing, educational, or travel-related work is strongly supported."),
        "business":  (1, "Long-distance business communication and international deals are favoured today."),
    },
    ("Mercury", 10): {
        "job":      (2, "Mercury in the 10th — your intellect is on full display at work. Bosses are impressed. Speak up."),
        "business": (2, "Business communication, pitches, and professional writing are outstanding today."),
        "politics": (1, "Your words carry authority and credibility in all public forums today."),
    },
    ("Mercury", 11): {
        "finances":  (1, "Mercury in the 11th supports financial planning and income through communication or media."),
        "job":       (1, "Professional networking and social connections bring tangible career benefits today."),
        "education": (1, "Group study, online courses, and collaborative learning are highly effective today."),
    },
    ("Mercury", 12): {
        "education": (-1, "Mercury in the 12th causes mental fogginess — revise existing material rather than starting new."),
        "finances":  (-1, "Hidden fees, miscommunications about money, or paperwork errors are possible — double-check."),
        "business":  (-1, "Communication delays may stall business dealings — follow up on everything proactively today."),
    },

    # ══════════ JUPITER ══════════
    ("Jupiter", 1): {
        "health":    (2, "Jupiter in the 1st bestows excellent vitality, optimism, and overall wellbeing today."),
        "education": (2, "Wisdom and understanding flow effortlessly — an auspicious day for deep learning of any kind."),
        "family":    (2, "Jupiter blesses the entire family with positivity, joy, and divine protection today."),
    },
    ("Jupiter", 2): {
        "finances": (2, "Jupiter in the 2nd — one of the finest wealth indicators. Income, savings, and family wealth benefit."),
        "family":   (2, "Warmth, prosperity, and abundance fill the home today. Elder blessings are very active."),
        "education": (1, "Communication and speech are eloquent — good for teaching, presentations, and debates."),
    },
    ("Jupiter", 3): {
        "education": (1, "Jupiter expands intellectual horizons — good for learning, short trips, and new skills today."),
        "sports":    (1, "Courage and wisdom combine for measured, intelligent competition today."),
        "business":  (1, "Wise communication and ethical business dealings are rewarded generously today."),
    },
    ("Jupiter", 4): {
        "family":    (2, "Jupiter in the 4th brings deep domestic happiness, peace at home, and blessings for mother."),
        "health":    (1, "Emotional and psychological wellbeing is excellent — feel at peace with yourself today."),
        "education": (1, "Home learning and foundational subjects are very well-supported today."),
    },
    ("Jupiter", 5): {
        "education": (2, "Jupiter in the 5th is the most auspicious placement for academic excellence and intelligence."),
        "love":      (2, "Pure, deep, and dharmic love is indicated — a beautiful day for romance and commitment."),
        "arts":      (2, "Jupiter in the 5th blesses creative brilliance — your art today carries wisdom and grace."),
    },
    ("Jupiter", 6): {
        "health":   (2, "Jupiter overcomes all health enemies — illness, debt, and rivals are all subdued today."),
        "job":      (2, "Workplace problems dissolve; your wisdom earns you respect and trust from all colleagues."),
        "finances": (1, "Debts can be cleared and financial obstacles overcome today with Jupiter's support."),
    },
    ("Jupiter", 7): {
        "married_life": (2, "Jupiter in the 7th is the ultimate blessing for marriage — wisdom, generosity, and joy between spouses."),
        "love":         (2, "Noble, sincere romantic energy today — relationships formed now have deep, lasting potential."),
        "business":     (2, "Partnership deals blessed by Jupiter — highly auspicious for signing agreements and forming alliances."),
    },
    ("Jupiter", 8): {
        "health":    (-1, "Jupiter in the 8th may expand hidden health issues — do not ignore persistent symptoms today."),
        "finances":  (-1, "Joint finances or inheritance matters may need careful handling — avoid all shortcuts."),
        "education": (1, "Research, occult learning, and investigation of hidden subjects are supported today."),
    },
    ("Jupiter", 9): {
        "education": (2, "Jupiter in its natural house — the finest day for philosophy, spirituality, and higher education."),
        "family":    (2, "Ancestral blessings and divine grace fill the family today. Father's situation improves."),
        "politics":  (2, "Fortune and dharma walk beside you in public life — a deeply auspicious day for leadership."),
    },
    ("Jupiter", 10): {
        "job":      (2, "Jupiter in the 10th — career success, promotions, and recognition from authority figures are strongly indicated."),
        "business": (2, "Ethical and wisdom-driven business decisions bring lasting rewards today. Trust your judgment."),
        "politics": (2, "Jupiter at the peak gives tremendous public respect, authority, and dharmic leadership today."),
    },
    ("Jupiter", 11): {
        "finances": (2, "Jupiter in the 11th is the most powerful wealth gain position — abundant income is indicated today."),
        "job":      (2, "Goals are achieved; ambitions are fulfilled; professional desires come to fruition today."),
        "family":   (2, "Celebrations, good news, and joyful gatherings are indicated in the family sphere today."),
    },
    ("Jupiter", 12): {
        "health":    (-1, "Jupiter in the 12th can indicate expenses through medical or institutional matters — monitor health."),
        "finances":  (-1, "Charitable or spiritual spending increases — budget accordingly but don't suppress generosity."),
        "education": (1, "Spiritual learning, meditation, and inner wisdom flourish with this placement today."),
    },

    # ══════════ VENUS ══════════
    ("Venus", 1): {
        "love":   (2, "Venus in the 1st makes you irresistibly attractive today — romance seeks you out effortlessly."),
        "arts":   (2, "Your aesthetic sense is divine today — art, beauty, and creativity flow at their finest."),
        "health": (1, "Venus in the 1st brings physical attractiveness and overall glow — you look and feel your best."),
    },
    ("Venus", 2): {
        "finances": (2, "Venus in the 2nd brings financial comforts, pleasures, and gentle but steady income gains."),
        "family":   (2, "Warmth, love, good food, and family togetherness define today beautifully."),
        "love":     (1, "Sweet, affectionate words and loving expressions flow naturally with your partner today."),
    },
    ("Venus", 3): {
        "arts":      (2, "Venus in the 3rd blesses music, writing, and all communication-based arts — a truly creative day."),
        "love":      (1, "Flirtatious, charming social energy makes all interactions light and romantic."),
        "education": (1, "Aesthetic subjects — art, music, design, literature — are powerfully supported today."),
    },
    ("Venus", 4): {
        "family": (2, "Venus in the 4th fills the home with love, beauty, and domestic happiness — a wonderful day."),
        "health": (1, "Emotional contentment from home life boosts your overall physical and mental wellbeing."),
        "love":   (1, "Comfort and security in romantic relationships — a good day to cosy up with your partner."),
    },
    ("Venus", 5): {
        "love":      (2, "Venus in the 5th is the pinnacle of romance — pure love, creative affection, and deep attraction."),
        "arts":      (2, "Venus in its natural house of art and beauty — everything you create today is inspired."),
        "education": (1, "Creative intelligence and all aesthetic subjects are brilliantly supported today."),
    },
    ("Venus", 6): {
        "health":   (1, "Venus in the 6th helps overcome illness through beauty routines, self-care, and rest."),
        "job":      (1, "Charming your way through workplace challenges — social skills resolve conflicts gracefully."),
        "finances": (-1, "Money spent on comforts and luxuries may exceed what was planned — be mindful today."),
    },
    ("Venus", 7): {
        "married_life": (2, "Venus in the 7th is the most auspicious sign for marriage — deep love, harmony, and mutual devotion."),
        "love":         (2, "Love is reciprocated fully today — a perfect day for romantic commitments or proposals."),
        "business":     (1, "Charm and persuasion work beautifully in business partnerships and client relations today."),
    },
    ("Venus", 8): {
        "love":     (-1, "Venus in the 8th can create secretive or complicated romantic situations — proceed with clarity."),
        "finances": (-1, "Joint finances and shared assets may require careful management — avoid joint speculation."),
        "arts":     (1, "Deep, transformative art from the subconscious — excellent for psychological or dark-themed creativity."),
    },
    ("Venus", 9): {
        "love":      (2, "Venus in the 9th brings a spiritually elevated, dharmic, and faithful quality to romance today."),
        "arts":      (2, "A day for philosophical art, devotional music, and creations that deeply touch the soul."),
        "education": (1, "Aesthetic higher education — fashion, fine arts, design, film — is well-supported today."),
    },
    ("Venus", 10): {
        "job":      (2, "Venus in the 10th — a glamorous, socially powerful day at work. You charm everyone above you."),
        "arts":     (2, "Public recognition for your artistic work is very likely today. Showcase your talent."),
        "politics": (1, "Your people skills and likability make you a magnet for public support today."),
    },
    ("Venus", 11): {
        "finances": (2, "Venus in the 11th brings pleasurable income and joyful financial gains — often through art or beauty."),
        "love":     (2, "Social gatherings lead to beautiful romantic connections — put yourself out there today."),
        "family":   (1, "Celebrations, gifts, and happy social events involving friends and family are likely."),
    },
    ("Venus", 12): {
        "love":     (1, "A deeply spiritual, private, and soulful day for love — introspection and inner romance."),
        "finances": (-1, "Venus in the 12th increases expenditure on pleasures, beauty, or entertainment — budget carefully."),
        "health":   (-1, "A tendency to overindulge in comforts or sweets today — practise moderation."),
    },

    # ══════════ SATURN ══════════
    ("Saturn", 1): {
        "health": (-2, "Saturn on your Moon sign brings fatigue and chronic issues to the fore — rest is essential."),
        "job":    (-1, "Responsibilities pile up and progress feels slow — stay disciplined, results will come."),
        "family": (-1, "A serious, heavy atmosphere at home — be patient and avoid pressuring family members."),
    },
    ("Saturn", 2): {
        "finances": (-2, "Saturn in the 2nd restricts financial flow — income is slow, expenditure feels oppressive."),
        "family":   (-2, "Karmic tensions in family relationships may surface — handle with maturity and patience."),
        "health":   (-1, "Throat, teeth, and speech-related issues may persist — do not neglect dental health today."),
    },
    ("Saturn", 3): {
        "job":       (1, "Saturn in the 3rd rewards disciplined, persistent effort — slow but steady wins the day."),
        "education": (-1, "Learning may feel laborious — short study sessions with frequent breaks are advised."),
        "sports":    (-1, "Avoid overexertion; Saturn can cause injury through fatigue if you push too hard today."),
    },
    ("Saturn", 4): {
        "family": (-2, "Kantaka Shani in the 4th brings domestic burden, property stress, and maternal concerns."),
        "health": (-1, "Chest, lungs, and emotional stability need attention — avoid cold and damp environments."),
        "job":    (-2, "Career obstacles and delays are likely today — keep expectations realistic and grounded."),
    },
    ("Saturn", 5): {
        "education": (-1, "Saturn in the 5th can make learning feel heavy — structure your studies very carefully."),
        "love":      (-1, "A serious, cautious tone enters romance — avoid over-analysing your relationship today."),
        "arts":      (-1, "Creative blocks are possible — discipline and daily practice will eventually break through."),
    },
    ("Saturn", 6): {
        "job":      (2, "Saturn in the 6th is a powerful placement for defeating competition through sheer endurance."),
        "health":   (1, "Disciplined health routines bring measurable improvements with Saturn in the 6th today."),
        "finances": (1, "Debts can be cleared through systematic effort — Saturn rewards diligent financial management."),
    },
    ("Saturn", 7): {
        "married_life": (-2, "Saturn in the 7th creates emotional distance with spouse — effort is needed to bridge the gap."),
        "love":         (-1, "A serious, heavy tone in romance — not the best day for fun and lightness in relationships."),
        "business":     (-1, "Partnership deals may face delays or legalistic complications — be patient and thorough."),
    },
    ("Saturn", 8): {
        "health":   (-2, "Saturn in the 8th is a chronic health warning — do not ignore any persistent symptoms today."),
        "finances": (-2, "Unexpected financial burdens, taxes, or debts may surface — ensure accounts are in order."),
        "job":      (-1, "Sudden setbacks at work are possible — stay calm and avoid panicking in any crisis."),
    },
    ("Saturn", 9): {
        "education": (-1, "Saturn in the 9th creates a demanding quality to learning — persist steadily without forcing."),
        "family":    (-1, "Father or paternal figures may be burdened or unwell — offer your support generously."),
        "politics":  (-1, "Public positioning requires extra effort today — avoid all controversial statements."),
    },
    ("Saturn", 10): {
        "job":      (1, "Saturn in the 10th builds career brick by brick — slow, disciplined effort creates lasting reputation."),
        "business": (1, "Long-term business decisions made today will have durable, structured, and lasting results."),
        "politics": (-1, "Responsibility in public office weighs heavily today — carry it with dignity and humility."),
    },
    ("Saturn", 11): {
        "finances": (1, "Saturn in the 11th — slow but certain gains through discipline and systematic effort today."),
        "job":      (1, "Professional networks built through sincerity and persistence are activated today."),
        "family":   (-1, "Social life and gatherings may feel obligatory or draining — manage your energy wisely."),
    },
    ("Saturn", 12): {
        "health":    (-1, "Saturn in the 12th can bring hidden chronic conditions to the surface — prioritise sleep."),
        "finances":  (-1, "Expenditure through institutional or foreign channels increases today — monitor carefully."),
        "education": (1, "Isolated, deep, meditative study is favoured — Saturn in the 12th supports spiritual learning."),
    },

    # ══════════ RAHU ══════════
    ("Rahu", 1): {
        "health": (-1, "Rahu in the 1st creates unusual or hard-to-diagnose health sensations — trust your instincts."),
        "love":   (1, "An unusual, unconventional attraction may captivate you today — proceed with discernment."),
        "job":    (1, "Rahu gives ambition and shrewdness — use it for strategic career moves today."),
    },
    ("Rahu", 2): {
        "finances": (-2, "Rahu in the 2nd is the classic deception placement — do NOT make large financial decisions today."),
        "family":   (-2, "Rahu in the family house creates a Grahan-like effect — miscommunication and confusion likely."),
        "health":   (-1, "Dietary extremes or food-related issues possible — eat simple, familiar food today."),
    },
    ("Rahu", 3): {
        "job":       (1, "Rahu in the 3rd sharpens ambition and clever thinking — excellent for media and tech work."),
        "education": (1, "Unconventional learning paths, digital platforms, and innovative subjects are strongly favoured."),
        "arts":      (1, "Rahu's eccentric creativity can produce groundbreaking art — push all the boundaries today."),
    },
    ("Rahu", 4): {
        "family":   (-1, "Rahu in the 4th creates restlessness at home and possible misunderstandings with mother."),
        "health":   (-1, "Anxiety, insomnia, and nervous tension associated with domestic issues — practise grounding."),
        "finances": (-1, "Property or real estate decisions may carry hidden complications today — do thorough due diligence."),
    },
    ("Rahu", 5): {
        "love":      (1, "Rahu creates intense, somewhat obsessive romantic attraction today — exciting but not always stable."),
        "education": (-1, "Mental confusion in studies today — avoid shortcuts; depth and clarity are what's needed."),
        "arts":      (1, "Experimental, boundary-pushing creative work can yield surprising and impressive results."),
    },
    ("Rahu", 6): {
        "job":      (2, "Rahu in the 6th gives a fierce competitive edge — rivals are confused and disadvantaged today."),
        "health":   (-1, "Unusual or viral illness possible — boost your immune system and avoid crowded places."),
        "finances": (1, "Clever, unorthodox financial strategies can yield gains — think well outside the box today."),
    },
    ("Rahu", 7): {
        "married_life": (-1, "Rahu in the 7th can bring unconventional tensions or deceptive elements into partnerships."),
        "love":         (1, "An intense, magnetic, perhaps foreign or unusual romantic connection is indicated today."),
        "business":     (-1, "Caution with contracts involving unknown or foreign parties — verify everything before signing."),
    },
    ("Rahu", 8): {
        "health":   (-2, "Rahu in the 8th is a serious health warning — avoid risky activities and physical extremes today."),
        "finances": (-2, "Sudden financial disruption through deception or hidden factors possible — guard your assets."),
        "job":      (-1, "Office politics and behind-the-scenes intrigue are at a high — stay completely out of all gossip."),
    },
    ("Rahu", 9): {
        "education": (-1, "Rahu in the 9th can create confusion in belief systems — seek real teachers, not shortcuts."),
        "politics":  (1, "Rahu's ambition in the 9th can bring sudden public fortune — but through unorthodox means."),
        "family":    (-1, "Father's situation may involve foreign matters or unconventional complications today."),
    },
    ("Rahu", 10): {
        "job":      (2, "Rahu in the 10th is extremely ambitious — sudden career rises and public recognition are possible."),
        "politics": (2, "Rahu gives unconventional but highly effective public influence today — use it wisely."),
        "business": (1, "Bold, disruptive business moves can succeed where conventional thinking completely fails."),
    },
    ("Rahu", 11): {
        "finances": (2, "Rahu in the 11th creates sudden, unexpected financial gains — often through tech or foreign sources."),
        "job":      (1, "Unconventional networking and digital connections can open unexpected professional doors today."),
        "love":     (1, "A surprising, unexpected romantic connection through social or digital channels is possible."),
    },
    ("Rahu", 12): {
        "finances": (-1, "Rahu in the 12th can cause financial leakage through foreign, digital, or hidden channels."),
        "health":   (-1, "Foreign-origin or mysterious health issues possible — avoid travel to polluted environments."),
        "love":     (1, "A secretive, private, or spiritually unusual romantic situation may quietly develop today."),
    },

    # ══════════ KETU ══════════
    ("Ketu", 1): {
        "health":    (-1, "Ketu in the 1st brings detachment from the body — watch for absent-minded injuries today."),
        "love":      (-1, "A sense of spiritual detachment may make emotional closeness feel difficult today."),
        "education": (1, "Past-life wisdom and deep intuition support scholarly and spiritual study today."),
    },
    ("Ketu", 2): {
        "finances":  (-1, "Ketu in the 2nd creates indifference to material wealth — be careful not to overlook important finances."),
        "family":    (-1, "A quiet, withdrawn feeling in family interactions today — solitude may be preferred."),
        "education": (1, "Ancient languages, Vedic subjects, and deep scriptural study are powerfully supported today."),
    },
    ("Ketu", 3): {
        "education": (1, "Ketu supports past-oriented learning today — history, mythology, and traditional subjects."),
        "sports":    (-1, "Detachment from competitive drive today — focus on personal best rather than the win."),
        "arts":      (1, "Ketu brings mystical, otherworldly creative depth — devotional music and spiritual art especially."),
    },
    ("Ketu", 4): {
        "family":    (-1, "Ketu in the 4th creates a sense of disconnection from home — you may feel rootless today."),
        "health":    (-1, "Vague, unspecified physical discomforts may appear — rest well and avoid overstimulation."),
        "education": (1, "Meditative and introspective study is favoured over active new learning today."),
    },
    ("Ketu", 5): {
        "love":      (-1, "Ketu in the 5th creates emotional detachment in romance — spiritual love over the physical."),
        "education": (2, "Ketu in the 5th gives profound past-life intelligence — spiritual subjects and ancient wisdom shine."),
        "arts":      (1, "Minimalist, spiritually infused art forms are deeply supported and inspired today."),
    },
    ("Ketu", 6): {
        "health":   (2, "Ketu in the 6th helps dissolve illness and defeats enemies through powerful spiritual protection."),
        "job":      (1, "Workplace enemies lose their power today — a mysterious karmic shield protects your interests."),
        "finances": (1, "Debts and obligations are gradually dissolved today through karmic intervention and grace."),
    },
    ("Ketu", 7): {
        "married_life": (-1, "Ketu in the 7th can create emotional separation or spiritual distance with spouse today."),
        "love":         (-1, "Detachment in romantic relationships — a partner may feel distant or hard to read."),
        "business":     (-1, "Partnership energy is low today — avoid new joint ventures or contractual agreements."),
    },
    ("Ketu", 8): {
        "health":    (-1, "Ketu in the 8th can bring karmic health challenges — heed your body's subtle signals today."),
        "finances":  (-1, "Inheritance or joint finance matters may have unexpected karmic complications today."),
        "education": (1, "Research into ancient wisdom, metaphysics, and hidden knowledge is powerfully supported."),
    },
    ("Ketu", 9): {
        "education": (2, "Ketu in the 9th gives moksha-oriented learning — the highest spiritual and philosophical insight."),
        "politics":  (-1, "Ketu in the 9th can cause sudden reversals of fortune in public life — stay humble."),
        "family":    (-1, "Father or guru figures may be distant or unavailable today — rely on your own inner wisdom."),
    },
    ("Ketu", 10): {
        "job":      (-1, "Ketu in the 10th can cause sudden career disruptions or detachment from professional ambition."),
        "business": (-1, "Unexpected reversals in business are possible today — review your strategy and protect assets."),
        "politics": (-1, "Public life is subject to karmic disruption — avoid making bold public declarations today."),
    },
    ("Ketu", 11): {
        "finances": (-1, "Gains are unpredictable today — avoid counting on any income that isn't already confirmed."),
        "love":     (1, "A spiritually deep, karmic romantic connection is possible through unusual circumstances."),
        "job":      (-1, "Professional goals may feel misaligned with your deeper purpose today — reflect, don't act impulsively."),
    },
    ("Ketu", 12): {
        "health":    (1, "Ketu in the 12th supports healing through rest, solitude, and deep spiritual practice."),
        "finances":  (-1, "Expenses through spiritual or charitable activities may feel heavy — but carry karmic merit."),
        "education": (2, "Ketu in the 12th is the finest placement for moksha-oriented learning and deep inner study."),
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Nakshatra modifier — adds flavour sentence per topic
# Used for BOTH natal Moon nakshatra (slow) AND transit Moon nakshatra (daily!)
# ─────────────────────────────────────────────────────────────────────────────

NAKSHATRA_FLAVOUR: dict[str, dict[str, str]] = {
    "Ashwini":           {"health": "Ashwini's swift healing energy supports quick recovery and vitality today.", "love": "Impulsive romantic gestures land particularly well under Ashwini."},
    "Bharani":           {"health": "Avoid overindulgence — Bharani's intensity can burn out the body if unchecked.", "love": "Deep, sensual, and intense romantic feelings are significantly heightened."},
    "Krittika":          {"job": "Sharp critical thinking helps you cut cleanly through workplace obstacles today.", "education": "Precision and focus are enhanced — ideal for all technical subjects."},
    "Rohini":            {"family": "Rohini's nourishing energy brings warmth, good food, and togetherness to the home.", "love": "Romance flourishes under Rohini's gentle, earthy, and beautiful charm."},
    "Mrigashira":        {"education": "Curiosity and the quest for knowledge are strongly heightened under Mrigashira today.", "love": "You are drawn to chase a new romantic interest with enthusiasm and delight."},
    "Ardra":             {"health": "Emotional storms are possible under Ardra — practise calming routines throughout the day.", "education": "Deep, penetrating intelligence for research and intense investigation."},
    "Punarvasu":         {"family": "Punarvasu brings renewal and fresh optimism back to all family relationships today.", "health": "Recovery and restoration are strongly supported under Punarvasu today."},
    "Pushya":            {"family": "Pushya is the most nourishing nakshatra — a beautiful day for bonding with family.", "finances": "Conservative, growth-oriented financial decisions are especially blessed today."},
    "Ashlesha":          {"business": "Ashlesha's natural shrewdness is excellent for negotiations and strategic business today.", "health": "Digestive sensitivity today — eat light and completely avoid processed food."},
    "Magha":             {"job": "Magha's royal energy supports authority, leadership, and bold ambition at work today.", "politics": "Ancestral power and natural authority significantly support your public standing."},
    "Purva Phalguni":    {"love": "A deeply romantic and pleasure-oriented day — enjoy life's beauties with your partner.", "arts": "Creative and aesthetic output is exceptionally inspired and beautiful today."},
    "Uttara Phalguni":   {"married_life": "Uttara Phalguni's stable, contractual energy powerfully supports lasting marital commitments.", "job": "Reliability and steady execution win you significant professional respect today."},
    "Hasta":             {"education": "Clever hands and a sharp mind — crafts, technical skills, and dexterity are all supported.", "business": "Sleight of hand in business — clever tactics and quick deals succeed splendidly today."},
    "Chitra":            {"arts": "Chitra's brilliant visual creativity makes today truly exceptional for design and aesthetics.", "love": "Your appearance and magnetic charm are at their peak today — make an effort to look your best."},
    "Swati":             {"business": "Swati's independent, trade-oriented energy strongly supports self-employment and commerce.", "love": "A free-spirited, non-possessive romantic energy serves your relationships very well today."},
    "Vishakha":          {"job": "Goal-oriented ambition is at a peak — push hard toward all your professional targets today.", "politics": "Vishakha's dual nature supports both spiritual and worldly political ambitions simultaneously."},
    "Anuradha":          {"family": "Deep, loyal friendships and cooperative family relationships are powerfully supported today.", "health": "Devotional and team-based healing — yoga class, group walks — is especially effective."},
    "Jyeshtha":          {"politics": "Jyeshtha's elder-statesman energy gives powerful authority and seniority in all public matters.", "job": "Protective of your professional domain today — colleagues deeply respect your seniority."},
    "Mula":              {"education": "Root-level investigation and getting to the very bottom of things — research excels today.", "health": "Avoid physical extremes today — Mula's energy can be destructive if completely unchecked."},
    "Purva Ashadha":     {"love": "Purva Ashadha's invincible optimism brings confidence and joyful boldness into romance.", "business": "Charging forward in business with great enthusiasm — an excellent day to initiate new ventures."},
    "Uttara Ashadha":    {"job": "Uttara Ashadha guarantees eventual victory through patient, deeply disciplined effort today.", "sports": "Endurance and determined effort guarantee impressive results in any sport today."},
    "Shravana":          {"education": "Shravana — the listener — excels at learning through listening, lectures, and audio content.", "family": "Deep listening and genuine empathy transform family relationships very positively today."},
    "Dhanishta":         {"finances": "Dhanishta's strong wealth energy makes today excellent for financial planning and accumulation.", "arts": "Music and all rhythm-based arts are especially powerful and deeply expressive today."},
    "Shatabhisha":       {"health": "Shatabhisha's potent healing energy strongly supports medical treatment and holistic therapies.", "education": "Unconventional scientific and healing subjects are deeply and powerfully supported today."},
    "Purva Bhadrapada":  {"education": "Intense, fiery intellectual energy today — great for tackling the most advanced academic challenges.", "love": "An unusual, deeply transformative romantic experience is distinctly possible today."},
    "Uttara Bhadrapada": {"health": "Deep rest and quiet solitude restore vital energy under Uttara Bhadrapada's stable influence.", "education": "Philosophical depth and spiritual learning are exceptionally and powerfully supported today."},
    "Revati":            {"love": "Revati's compassionate, divine love creates a beautifully tender and deeply heartfelt romantic day.", "arts": "Creative work with a spiritual or universal theme resonates with extraordinary depth today."},
}

# ─────────────────────────────────────────────────────────────────────────────
# Tithi modifier — CHANGES EVERY ~24 HOURS (key driver of daily uniqueness)
# ─────────────────────────────────────────────────────────────────────────────

TITHI_FLAVOUR: dict[str, dict[str, str]] = {
    "Pratipada": {
        "job":       "Pratipada favours fresh starts — a strong day to kick off new projects.",
        "health":    "A light, new-beginning tithi — perfect for starting a fitness or diet routine.",
        "business":  "New ventures launched on Pratipada gain durable, forward momentum.",
    },
    "Dwitiya": {
        "family":    "Dwitiya supports nurturing bonds — reach out to a family member you've been neglecting.",
        "finances":  "Steady, conservative money moves are favoured under Dwitiya today.",
        "love":      "Gentle, growing affection — a tender tithi for early-stage romance.",
    },
    "Tritiya": {
        "sports":    "Tritiya brings competitive vigour — push hard in any physical contest today.",
        "business":  "Bold sales moves and outreach pitches land well under Tritiya.",
        "education": "Active, restless intelligence — best used on challenging problems today.",
    },
    "Chaturthi": {
        "health":    "Chaturthi is ruled by Ganesha — obstacles dissolve, but avoid heavy meals today.",
        "education": "Mental clarity for problem-solving peaks under Chaturthi.",
        "job":       "A tithi for removing obstacles — clear that one blocker that has been delaying you.",
    },
    "Panchami": {
        "education": "Panchami is excellent for learning — knowledge sticks deeply today.",
        "love":      "Playful, charming romantic energy under Panchami — keep things light.",
        "finances":  "A good day for small, smart investments and money-related research.",
    },
    "Shashthi": {
        "job":       "Shashthi favours discipline and routine — clear backlogs and finish pending tasks.",
        "health":    "Recovery and healing are strongly supported under Shashthi today.",
        "sports":    "Endurance training works well — Shashthi rewards steady, repeated effort.",
    },
    "Saptami": {
        "business":  "Saptami supports trade, travel, and dealings — a productive commercial day.",
        "politics":  "Public visibility and social influence are favourable today.",
        "job":       "Travel and movement bring opportunity today — say yes to that meeting.",
    },
    "Ashtami": {
        "health":    "Ashtami can be intense — avoid risky physical activity and very rich food.",
        "finances":  "Avoid major financial commitments on Ashtami — wait a day if you can.",
        "love":      "Emotionally charged tithi — handle romantic conversations with extra care.",
    },
    "Navami": {
        "family":    "Navami strengthens family unity — a great day for family gatherings.",
        "education": "Devotional, spiritual, and philosophical study flourishes under Navami.",
        "arts":      "Creative work touched by devotion or higher purpose excels today.",
    },
    "Dashami": {
        "job":       "Dashami brings stability and completion — finish what you started.",
        "business":  "Closing deals and signing agreements is very well-timed today.",
        "married_life": "A stabilising tithi for marriage — small commitments deepen the bond.",
    },
    "Ekadashi": {
        "health":    "Ekadashi is sacred for fasting — light food and prayer cleanse body and mind.",
        "education": "Spiritual and philosophical study is exceptionally rewarding today.",
        "arts":      "A meditative, refined creative tithi — subtle art over grand statements.",
    },
    "Dwadashi": {
        "family":    "Dwadashi after Ekadashi brings renewed family warmth and gratitude.",
        "finances":  "A balanced day for moderate financial planning — review more than act.",
        "health":    "Break your fast gently — Dwadashi rewards moderation in eating.",
    },
    "Trayodashi": {
        "love":      "Trayodashi (Pradosh) carries passionate, intense energy — romance is heightened.",
        "arts":      "Creative expression is bold and dramatic today — let the work be intense.",
        "politics":  "A powerful tithi for public action — bold statements resonate strongly.",
    },
    "Chaturdashi": {
        "health":    "Chaturdashi can stir restlessness — practise grounding and avoid arguments.",
        "job":       "A turbulent tithi — avoid major workplace confrontations today.",
        "finances":  "Defer speculative or risky financial moves — wait one more day.",
    },
    "Purnima": {
        "love":      "Purnima — the full moon — amplifies all romantic feeling. Magical for love.",
        "arts":      "Creativity peaks under the full moon's light — produce your best work tonight.",
        "family":    "Family gatherings under the full moon are deeply auspicious and bonding.",
    },
    "Amavasya": {
        "health":    "Amavasya — new moon — energy is low; rest deeply and avoid new ventures.",
        "family":    "Honour ancestors today; quiet, inward family time is favoured.",
        "finances":  "Defer all major financial decisions to a future tithi — Amavasya is for reflection.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Dasha colour modifier
# ─────────────────────────────────────────────────────────────────────────────

DASHA_COLOUR: dict[str, dict[str, str]] = {
    "Sun":     {"job": "Sun Dasha magnifies all career ambitions — authority and recognition are central themes now.", "health": "Guard vitality carefully; Sun Dasha burns bright but can deplete reserves."},
    "Moon":    {"family": "Moon Dasha heightens emotional sensitivity in all family interactions throughout this period.", "love": "Romantic feelings are powerfully amplified and deeply felt during Moon Dasha."},
    "Mars":    {"sports": "Mars Dasha is the finest period for physical performance and competitive drive.", "business": "Aggressive action and bold decisions define this active Mars Dasha phase."},
    "Mercury": {"education": "Mercury Dasha exceptionally supports learning, writing, and all intellectual growth.", "business": "Sharp negotiation and analytical thinking are your greatest assets in Mercury Dasha."},
    "Jupiter": {"education": "Jupiter Dasha brings profound wisdom and academic excellence — a golden phase for study.", "finances": "Jupiter Dasha is associated with dharmic wealth and long-term financial growth."},
    "Venus":   {"love": "Venus Dasha heightens the desire for love, beauty, and romantic fulfilment deeply.", "arts": "Creative output in Venus Dasha carries extraordinary beauty and lasting impact."},
    "Saturn":  {"job": "Saturn Dasha rewards disciplined, long-term professional effort with durable results.", "health": "Saturn Dasha emphasises chronic health management — routine and discipline are absolutely key."},
    "Rahu":    {"business": "Rahu Dasha fuels ambition and unconventional strategies that can yield dramatic gains.", "politics": "Rahu Dasha brings sudden rises in public life — handle fame and power with great humility."},
    "Ketu":    {"education": "Ketu Dasha is excellent for spiritual learning, past-life wisdom, and detachment from materialism.", "health": "Ketu Dasha can surface karmic health patterns — holistic and spiritual healing is most effective."},
}

# ─────────────────────────────────────────────────────────────────────────────
# Paksha modifier
# ─────────────────────────────────────────────────────────────────────────────

PAKSHA_NOTES = {
    "Shukla":  "🌕 Shukla Paksha (waxing Moon) — energy builds, new beginnings are auspicious, emotions rise.",
    "Krishna": "🌑 Krishna Paksha (waning Moon) — introspection, completion, releasing what no longer serves you.",
}

# Paksha-flavoured per-topic micro-lines (adds extra daily-level variety since
# paksha swaps every ~15 days and pairs differently with each topic).
PAKSHA_TOPIC_LINE: dict[str, dict[str, str]] = {
    "Shukla": {
        "job":      "Waxing Moon builds momentum — push initiatives forward today.",
        "business": "Shukla Paksha favours expansion and new client outreach.",
        "love":     "Growing Moon nurtures fresh attraction and new romantic possibilities.",
        "finances": "An auspicious paksha for starting investments and savings plans.",
        "education":"Building knowledge under Shukla Paksha sticks well — start new topics.",
    },
    "Krishna": {
        "job":      "Waning Moon favours closing out work — finish, file, archive, and tidy.",
        "business": "Krishna Paksha favours collections, reviews, and pruning underperformers.",
        "love":     "Reflective Moon — focus on understanding your partner rather than pursuing.",
        "finances": "A paksha for reviewing accounts and clearing debts rather than expanding.",
        "education":"Revision over new material — Krishna Paksha consolidates learning.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Moon-degree-in-sign "intensity" — early/middle/late changes within 2.5 days
# ─────────────────────────────────────────────────────────────────────────────

def _moon_intensity_label(degree_in_sign: float) -> str:
    """Return 'early', 'middle', or 'late' based on Moon's degree in its current sign."""
    if degree_in_sign < 10.0:
        return "early"
    elif degree_in_sign < 20.0:
        return "middle"
    else:
        return "late"


MOON_INTENSITY_LINE: dict[str, dict[str, str]] = {
    "early": {
        "family":    "Moon in early degrees of its sign — emotional energy is fresh and outward-facing.",
        "love":      "Early-degree Moon brings new sparks and curious romantic energy.",
        "health":    "Early-degree Moon: vitality is fresh — a good window to begin a new health habit.",
        "job":       "Early-degree Moon supports kick-off energy — start the day's biggest task first.",
    },
    "middle": {
        "family":    "Mid-degree Moon brings settled, balanced emotional warmth at home.",
        "love":      "Mid-degree Moon supports stable, deepening romantic conversation.",
        "health":    "Mid-degree Moon: steady physical energy — push through your routine confidently.",
        "job":       "Mid-degree Moon is the productivity sweet-spot — execute the plan today.",
    },
    "late": {
        "family":    "Late-degree Moon — emotions are transitioning; be patient with family mood swings.",
        "love":      "Late-degree Moon: prepare for tomorrow's shift; today is for closure conversations.",
        "health":    "Late-degree Moon — energy is winding down; prioritise rest tonight.",
        "job":       "Late-degree Moon favours wrapping up rather than starting fresh.",
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# Weekday rituals
# ─────────────────────────────────────────────────────────────────────────────

DAY_RITUALS: dict[str, tuple[str, str]] = {
    "Sunday":    ("☀️ Today is *Ravivar (Sunday)*",    "Offer water (Arghya) to the Sun at sunrise. Eat without salt for at least one meal. Wear saffron or orange. Donate wheat or jaggery to the needy."),
    "Monday":    ("🌙 Today is *Somvar (Monday)*",     "Offer milk to a Shivlinga. Wear white. Fast if possible. Chant Om Namah Shivaya 108 times. Donate rice or white cloth."),
    "Tuesday":   ("🔴 Today is *Mangalvar (Tuesday)*", "Visit a Hanuman temple. Donate red lentils (masoor dal) or red cloth. Wear red or coral. Chant Hanuman Chalisa."),
    "Wednesday": ("💚 Today is *Budhvar (Wednesday)*", "Feed green grass to cows or donate green moong. Wear green or emerald. Read and study — Mercury blesses intellectual work on His day."),
    "Thursday":  ("🟡 Today is *Guruvaar (Thursday)*", "Worship your Guru or Lord Vishnu. Donate yellow gram (chana dal) or turmeric. Wear yellow. Read Vishnu Sahasranama."),
    "Friday":    ("⚪ Today is *Shukravar (Friday)*",  "Offer white flowers to Goddess Lakshmi. Donate sugar, white rice, or dairy. Wear white or pastel. Chant Shri Suktam."),
    "Saturday":  ("🪐 Today is *Shanivar (Saturday)*", "Pour mustard oil on a Shani idol. Feed crows and the poor. Donate black sesame, iron, or dark blue cloth. Recite Shani Stotra."),
}

# ─────────────────────────────────────────────────────────────────────────────
# Auspicious timings (per weekday, IST)
# ─────────────────────────────────────────────────────────────────────────────

ABHIJIT_KAAL = {
    "Sunday": "11:56 – 12:48", "Monday": "11:56 – 12:48",
    "Tuesday": "11:55 – 12:47", "Wednesday": "11:55 – 12:47",
    "Thursday": "11:54 – 12:46", "Friday": "11:54 – 12:46",
    "Saturday": "11:53 – 12:45",
}
AMRIT_KAAL = {
    "Sunday": "13:24 – 15:00", "Monday": "15:12 – 16:48",
    "Tuesday": "06:00 – 07:36", "Wednesday": "16:36 – 18:12",
    "Thursday": "07:48 – 09:24", "Friday": "09:00 – 10:36",
    "Saturday": "10:48 – 12:24",
}
RAHU_KAAL = {
    "Sunday": "17:00 – 18:30", "Monday": "07:30 – 09:00",
    "Tuesday": "15:00 – 16:30", "Wednesday": "12:00 – 13:30",
    "Thursday": "13:30 – 15:00", "Friday": "10:30 – 12:00",
    "Saturday": "09:00 – 10:30",
}
YAMGHANT = {
    "Sunday": "12:00 – 13:30", "Monday": "10:30 – 12:00",
    "Tuesday": "09:00 – 10:30", "Wednesday": "07:30 – 09:00",
    "Thursday": "06:00 – 07:30", "Friday": "15:00 – 16:30",
    "Saturday": "13:30 – 15:00",
}

# ─────────────────────────────────────────────────────────────────────────────
# Dynamic Do / Don't signals
# ─────────────────────────────────────────────────────────────────────────────

DO_DONT_SIGNALS: dict[tuple[str, int], tuple[str, str]] = {
    ("Moon",    3):  ("Begin important work or journeys today — Moon supports forward momentum.",                      ""),
    ("Moon",    6):  ("Push through health routines and exercise — today's energy fully supports discipline.",         ""),
    ("Moon",   11):  ("Follow up on pending income and financial goals — Moon in the 11th delivers results.",          ""),
    ("Moon",    1):  ("",                                                                                               "Avoid starting anything new today — Janma Rashi Moon brings delays and obstacles."),
    ("Moon",    8):  ("",                                                                                               "Avoid major decisions today — Moon in the 8th creates emotional turbulence."),
    ("Moon",    4):  ("",                                                                                               "Avoid confrontations at home — Moon in the 4th heightens emotional sensitivity greatly."),
    ("Jupiter", 9):  ("Seek blessings from your Guru or elders today — Jupiter in the 9th multiplies all efforts.",   ""),
    ("Jupiter", 7):  ("Sign partnership agreements or commit to an alliance today — Jupiter blesses all contracts.",   ""),
    ("Jupiter",11):  ("Submit applications, proposals, or investment plans today — gains are strongly supported.",     ""),
    ("Venus",   7):  ("Express your love openly today — it will be received warmly and fully reciprocated.",           ""),
    ("Venus",   5):  ("Go on a date, create art, or do something beautiful — Venus in the 5th richly rewards it.",    ""),
    ("Mars",    6):  ("Take on your toughest challenge today — Mars in the 6th gives you power to conquer it.",       ""),
    ("Mars",   10):  ("Make the bold professional move you have been postponing — Mars in the 10th gives courage.",    ""),
    ("Mars",    3):  ("Act decisively on your plans today — Mars in the 3rd completely eliminates hesitation.",        ""),
    ("Mars",    2):  ("",                                                                                               "Do NOT make impulsive financial decisions — Mars in the 2nd triggers dangerous financial recklessness."),
    ("Mars",    4):  ("",                                                                                               "Avoid arguments with family today — Mars in the 4th turns small friction into major conflict."),
    ("Mars",    7):  ("",                                                                                               "Avoid picking battles with your partner or associates — Mars in the 7th is highly combustible."),
    ("Mars",    8):  ("",                                                                                               "Avoid risky physical activities, rash driving, and extreme sports — injury risk is elevated today."),
    ("Saturn",  6):  ("Put in systematic, disciplined effort today — Saturn in the 6th guarantees eventual reward.",   ""),
    ("Saturn", 10):  ("Focus on long-term professional goals today — Saturn in the 10th builds lasting reputation.",   ""),
    ("Saturn",  4):  ("",                                                                                               "Avoid property disputes and major home decisions today — Saturn in the 4th brings complications."),
    ("Saturn",  7):  ("",                                                                                               "Give your partner space today — Saturn in the 7th creates distance that needs patient bridging."),
    ("Saturn",  8):  ("",                                                                                               "Do not take financial risks or ignore health symptoms today — Saturn in the 8th amplifies all consequences."),
    ("Rahu",    2):  ("",                                                                                               "Do NOT buy, sell, or lend large amounts today — Rahu in the 2nd creates serious risk of financial deception."),
    ("Rahu",   10):  ("Use bold, unconventional tactics at work today — Rahu in the 10th rewards the daring.",         ""),
    ("Rahu",   11):  ("Explore digital or foreign income opportunities today — Rahu in the 11th favours the unusual.", ""),
    ("Rahu",    8):  ("",                                                                                               "Avoid risky, speculative, or extreme activities today — Rahu in the 8th magnifies all hidden dangers."),
    ("Mercury", 3):  ("Send that proposal, email, or business pitch today — Mercury in the 3rd delivers powerfully.",  ""),
    ("Mercury", 7):  ("Sign contracts and legal documents today — Mercury in the 7th is ideal for all agreements.",    ""),
    ("Mercury", 8):  ("",                                                                                               "Read every document twice before signing — Mercury in the 8th hides critical errors in the fine print."),
    ("Mercury",12):  ("",                                                                                               "Avoid finalising communications or contracts today — Mercury in the 12th invites miscommunication."),
    ("Sun",    10):  ("Showcase your work and speak up in meetings — Sun in the 10th makes leaders take notice.",      ""),
    ("Sun",     6):  ("Confront difficult situations or resolve workplace conflicts today — Sun in the 6th wins.",      ""),
    ("Sun",     8):  ("",                                                                                               "Avoid confronting authority figures today — Sun in the 8th makes you vulnerable to power plays."),
    ("Sun",    12):  ("",                                                                                               "Work quietly behind the scenes today — Sun in the 12th makes public-facing actions less effective."),
    ("Ketu",   12):  ("Meditate, practise yoga, or engage in spiritual study — Ketu in the 12th deeply rewards it.",   ""),
    ("Ketu",    6):  ("Pray for protection from enemies and unseen obstacles — Ketu in the 6th provides spiritual shielding.", ""),
    ("Ketu",   10):  ("",                                                                                               "Avoid making bold public declarations today — Ketu in the 10th can cause sudden karmic reversals."),
    ("Venus",  12):  ("",                                                                                               "Avoid overspending on luxuries or entertainment today — Venus in the 12th quietly drains the budget."),
    ("Venus",   6):  ("",                                                                                               "Avoid lending money to friends or lovers today — Venus in the 6th complicates financial generosity."),
}

# ─────────────────────────────────────────────────────────────────────────────
# Daily seed — changes every day, used to rotate sentences and break ties
# ─────────────────────────────────────────────────────────────────────────────

def _daily_seed() -> int:
    """Integer that changes every calendar day (YYYYMMDD)."""
    now = datetime.now()
    return now.year * 10000 + now.month * 100 + now.day


# ─────────────────────────────────────────────────────────────────────────────
# Ephemeris helpers
# ─────────────────────────────────────────────────────────────────────────────

def _get_transit_positions() -> dict[str, dict]:
    from utils.config import planets as PLANET_IDS
    swe.set_sid_mode(swe.SIDM_LAHIRI)
    now = datetime.now(timezone.utc)
    jd = swe.julday(now.year, now.month, now.day, now.hour + now.minute / 60.0)
    out = {}
    for name, pid in PLANET_IDS.items():
        lon = swe.calc_ut(jd, pid, swe.FLG_SIDEREAL)[0][0]
        if name == "Ketu":
            lon = (lon + 180.0) % 360.0
        si = int(lon // 30)
        deg = lon % 30
        ni = int(lon // 13.3333333) % 27
        pada = int((lon % 13.3333333) // 3.3333333) + 1
        s = "neutral"
        if signs[si] == EXALTED.get(name): s = "exalted"
        elif signs[si] in OWN_SIGNS.get(name, set()): s = "own sign"
        elif signs[si] == DEBILITATED.get(name): s = "debilitated"
        out[name] = {
            "sign": signs[si], "degree": round(deg, 2),
            "nakshatra": nakshatras[ni], "pada": pada,
            "longitude": round(lon, 4), "strength": s,
        }
    return out


def _get_today_tithi() -> dict:
    now = datetime.now(timezone.utc)
    jd = swe.julday(now.year, now.month, now.day, now.hour + now.minute / 60.0)
    sl = swe.calc_ut(jd, swe.SUN, swe.FLG_SWIEPH)[0][0]
    ml = swe.calc_ut(jd, swe.MOON, swe.FLG_SWIEPH)[0][0]
    diff = (ml - sl) % 360.0
    tn = int(diff / 12.0) + 1
    pk = "Shukla" if tn <= 15 else "Krishna"
    nm = TITHI_NAMES[(tn - 1) % 15]
    if tn == 15: nm = "Purnima"
    elif tn == 30: nm = "Amavasya"
    return {"number": tn, "name": nm, "paksha": pk}


def _house_from(ref_sign: str, transit_sign: str) -> int:
    return ((SIGN_INDEX[transit_sign] - SIGN_INDEX[ref_sign]) % 12) + 1


# ─────────────────────────────────────────────────────────────────────────────
# Topic signal collector + paragraph builder
# ─────────────────────────────────────────────────────────────────────────────

TOPIC_TITLES = {
    "family":       "👨‍👩‍👧 FAMILY LIFE",
    "married_life": "💑 MARRIED LIFE & SPOUSE",
    "love":         "💕 LOVE LIFE",
    "health":       "🏥 HEALTH & WELLBEING",
    "education":    "📚 EDUCATION & LEARNING",
    "business":     "🏢 BUSINESS & TRADE",
    "job":          "💼 JOB & CAREER",
    "finances":     "💰 FINANCIAL OUTLOOK",
    "arts":         "🎨 ARTS & CREATIVITY",
    "sports":       "🏆 SPORTS & ATHLETICS",
    "politics":     "🏛️ POLITICS & PUBLIC LIFE",
}

TOPIC_ORDER = [
    "family", "married_life", "love", "health", "education",
    "business", "job", "finances", "arts", "sports", "politics",
]

PLANET_LOOP = ["Sun", "Moon", "Mercury", "Venus", "Mars", "Jupiter", "Saturn", "Rahu", "Ketu"]


def _build_topic_paragraph(
    topic: str,
    transits: dict[str, dict],
    moon_sign: str,
    moon_nakshatra: str,
    dasha_lord: str,
    antar_lord: str,
    tithi_name: str,
    paksha: str,
    seed: int,
) -> tuple[str, str]:
    """
    Build the per-topic paragraph.

    Daily-changing inputs (so output differs each day):
      - tithi_name / paksha      → changes every ~24h
      - transits["Moon"]         → changes house every ~2.5d, nakshatra ~daily
      - seed                     → changes every calendar day
      - weekday rotation         → 7-day cycle on dasha lord choice
    """
    positives: list[str] = []
    negatives: list[str] = []
    total_weight = 0

    # ── Base planet signals ─────────────────────────────────────────────────
    for planet in PLANET_LOOP:
        if planet not in transits:
            continue
        h = _house_from(moon_sign, transits[planet]["sign"])
        key = (planet, h)
        if key not in SIGNALS:
            continue
        topic_signals = SIGNALS[key]
        if topic not in topic_signals:
            continue
        weight, text = topic_signals[topic]
        total_weight += weight

        s = transits[planet]["strength"]
        if s == "exalted":
            text = text.rstrip(".") + " (especially powerful — planet is exalted today)."
            total_weight += 1
        elif s == "debilitated":
            text = text.rstrip(".") + " (somewhat weakened — planet is debilitated today)."
            total_weight -= 1

        if weight > 0:
            positives.append(text)
        else:
            negatives.append(text)

    # ── Transit Moon's nakshatra flavour for THIS topic (DAILY CHANGE) ──────
    transit_moon_nak = transits.get("Moon", {}).get("nakshatra", "")
    transit_nak_flavours = NAKSHATRA_FLAVOUR.get(transit_moon_nak, {})
    if topic in transit_nak_flavours:
        positives.append(f"_Today's Moon in {transit_moon_nak}: {transit_nak_flavours[topic]}_")

    # ── Natal nakshatra flavour (rotated every other day) ────────────────────
    natal_nak_flavours = NAKSHATRA_FLAVOUR.get(moon_nakshatra, {})
    if topic in natal_nak_flavours and (seed % 2 == 0):
        positives.append(f"_Your natal nakshatra ({moon_nakshatra}): {natal_nak_flavours[topic]}_")

    # ── Tithi flavour (DAILY CHANGE) ─────────────────────────────────────────
    tithi_flavours = TITHI_FLAVOUR.get(tithi_name, {})
    if topic in tithi_flavours:
        positives.append(f"_{paksha} {tithi_name}: {tithi_flavours[topic]}_")

    # ── Paksha-topic micro-line (changes every ~15 days; rotates by seed) ───
    paksha_topic = PAKSHA_TOPIC_LINE.get(paksha, {})
    if topic in paksha_topic and (seed % 3 == 0):
        positives.append(f"_{paksha_topic[topic]}_")

    # ── Moon intensity (early / middle / late degrees, changes ~10 days) ────
    moon_deg = transits.get("Moon", {}).get("degree", 0.0)
    intensity = _moon_intensity_label(moon_deg)
    intensity_topic = MOON_INTENSITY_LINE.get(intensity, {})
    if topic in intensity_topic and (seed % 4 in (0, 1)):
        positives.append(f"_{intensity_topic[topic]}_")

    # ── Dasha colour (rotate which lord gets featured by day-of-week) ───────
    weekday_idx = datetime.now().weekday()
    lords = [dasha_lord, antar_lord]
    chosen_lord = lords[weekday_idx % 2] if lords[0] and lords[1] else (dasha_lord or antar_lord)
    if chosen_lord:
        dc = DASHA_COLOUR.get(chosen_lord, {})
        if topic in dc:
            positives.append(f"_({chosen_lord} Dasha: {dc[topic]})_")

    # ── Empty-day fallback (rotates 4 ways) ─────────────────────────────────
    if not positives and not negatives:
        quiet_variants = [
            "A quiet, unremarkable day for this area. Maintain your routine steadily.",
            "Steady-state energy here today — no major movement, but no setbacks either.",
            "A neutral, low-key day for this domain. Use the calm to plan ahead.",
            "Planetary attention is elsewhere today — this area runs smoothly on auto-pilot.",
        ]
        return "➖", "  _" + quiet_variants[seed % len(quiet_variants)] + "_"

    parts = []
    if positives:
        parts.append("  " + " ".join(positives))
    if negatives:
        connector = "\n\n  However, stay cautious: " if positives else "  ⚠️ "
        parts.append(connector + " ".join(negatives))

    para = "".join(parts)

    if total_weight >= 4:    verdict = "⭐"
    elif total_weight >= 2:  verdict = "✅"
    elif total_weight == 1:  verdict = "🔶"
    elif total_weight == 0:  verdict = "➖"
    elif total_weight >= -2: verdict = "⚠️"
    else:                    verdict = "🔴"

    return verdict, para


# ─────────────────────────────────────────────────────────────────────────────
# MASTER FUNCTION
# ─────────────────────────────────────────────────────────────────────────────

def generate_daily_forecast(
    kundli_result: dict,
    name: str = "",
    gender: str = "",
) -> list[str]:
    planets_data = kundli_result.get("planets_data", [])
    dasha_data   = kundli_result.get("dasha", {})

    natal_moon  = next((p for p in planets_data if p["name"] == "Moon"), None)
    natal_lagna = next((p for p in planets_data if p["name"] == "Ascendant"), None)

    moon_sign  = natal_moon["zodiac"]              if natal_moon  else "Aries"
    moon_nak   = natal_moon.get("Nakshatra", "Ashwini") if natal_moon else "Ashwini"
    lagna_sign = natal_lagna["zodiac"]             if natal_lagna else "Aries"

    current    = dasha_data.get("current", {})
    maha_lord  = current.get("mahadasha", "—")
    antar_lord = current.get("antardasha", "—")

    now      = datetime.now()
    weekday  = now.strftime("%A")
    date_str = now.strftime("%d %B %Y")
    transits = _get_transit_positions()
    tithi    = _get_today_tithi()
    seed     = _daily_seed()

    gender_icon = "♂️" if gender.lower() == "male" else "♀️" if gender.lower() == "female" else "🔱"

    # ── Sade Sati / Dhaiya ──
    saturn_h_moon = _house_from(moon_sign, transits.get("Saturn", {}).get("sign", moon_sign))
    sade_active   = saturn_h_moon in {12, 1, 2}
    dhaiya_active = saturn_h_moon in {4, 8}
    SADE_PHASE    = {12: "Rising Phase (12th)", 1: "Peak Phase — Janma Shani", 2: "Setting Phase (2nd)"}
    DHAIYA_DESC   = {4: "Career & domestic obstacles (Kantaka Shani)", 8: "Sudden setbacks & health strain (Ashtama Shani)"}

    # ── Moon effect ──
    moon_h_today = _house_from(moon_sign, transits.get("Moon", {}).get("sign", moon_sign))
    MOON_EFFECTS = {
        1:  ("Janma Rashi — low energy, avoid new starts", False),
        2:  ("Family & speech stress, watch emotions", False),
        3:  ("Courage, travel, bold initiative", True),
        4:  ("Emotional unrest at home, mother's health", False),
        5:  ("Romance, creativity, intelligence peak", True),
        6:  ("Victory over enemies, strong health, work success", True),
        7:  ("Relationship sensitivity, journey possible", False),
        8:  ("Hidden obstacles, health watch, avoid big decisions", False),
        9:  ("Fortune, spirituality, elder blessings", True),
        10: ("Career recognition, professional peak", True),
        11: ("Gains, income, wish fulfilment — excellent", True),
        12: ("Expenditure, isolation, spiritual retreat", False),
    }
    moon_effect_label, moon_benefic = MOON_EFFECTS.get(moon_h_today, ("Neutral", True))

    # ── Overall day score ──
    total_score = 0
    for pl in PLANET_LOOP:
        if pl not in transits: continue
        h = _house_from(moon_sign, transits[pl]["sign"])
        for topic_sigs in SIGNALS.get((pl, h), {}).values():
            total_score += topic_sigs[0]

    if   total_score >= 15: day_label, day_desc = "⭐ Exceptional Day", "Rare planetary alignment in your favour — act boldly and seize every opportunity today."
    elif total_score >= 8:  day_label, day_desc = "✅ Very Good Day",   "Planetary energies are broadly supportive. Push forward with confidence today."
    elif total_score >= 2:  day_label, day_desc = "🔶 Good Day",        "A positive day overall with some areas to navigate carefully."
    elif total_score >= -5: day_label, day_desc = "🔸 Mixed Day",        "A day of balanced energies — steady progress with mindful, careful action."
    elif total_score >= -12:day_label, day_desc = "⚠️ Challenging Day",  "Planetary pressures are active. Stay patient, grounded, and avoid all impulsive moves."
    else:                   day_label, day_desc = "🔴 Difficult Day",    "Heavy planetary tensions today. Rest, reflect, and avoid all new beginnings."

    messages = []

    # ── MSG 1: Header + Panchang ──
    day_icon, day_ritual = DAY_RITUALS.get(weekday, ("🔱 Today", ""))
    header = (
        f"🌅 *Good Morning{', ' + name if name else ''} {gender_icon}*\n"
        f"📅 *{weekday}, {date_str}*\n\n"
        f"🔱 *HORA DAILY RASHIFAL*\n"
        f"{'─' * 30}\n\n"
        f"📿 *Panchang*\n"
        f"  🗓️ Tithi: *{tithi['name']}* ({tithi['paksha']} Paksha)\n"
        f"  _{PAKSHA_NOTES[tithi['paksha']]}_\n"
        f"  🌙 Rashi (Moon Sign): *{moon_sign}*\n"
        f"  🌟 Janma Nakshatra: *{moon_nak}*\n"
        f"  ⬆️ Lagna: *{lagna_sign}*\n"
        f"  ⏳ Mahadasha: *{maha_lord}* | Antardasha: *{antar_lord}*\n\n"
        f"{'─' * 30}\n"
        f"*{day_label}*\n"
        f"_{day_desc}_"
    )
    if sade_active:
        header += (f"\n\n🚨 *SADE SATI ACTIVE — {SADE_PHASE[saturn_h_moon]}*\n"
                   f"_Saturn transiting your {saturn_h_moon}th from Moon. "
                   f"Patience and karmic discipline are essential right now._")
    elif dhaiya_active:
        header += (f"\n\n⚠️ *KANTAKA SHANI (Dhaiya) — {DHAIYA_DESC[saturn_h_moon]}*\n"
                   f"_Stay grounded and avoid impulsive changes in the affected areas._")
    messages.append(header)

    # ── MSG 2: Today's planets ──
    pos_lines = [f"🌍 *TODAY'S PLANETS*\n{'─' * 30}"]
    for pl in PLANET_LOOP:
        t = transits.get(pl, {})
        if not t: continue
        h = _house_from(moon_sign, t["sign"])
        icon = PLANET_ICONS.get(pl, "⭐")
        stag = {"exalted": " ✨EXALTED", "own sign": " 🟢OWN SIGN", "debilitated": " 🔻DEBIL."}.get(t["strength"], "")
        pos_lines.append(
            f"{icon} *{pl}* in {t['sign']} {t['degree']}°{stag}\n"
            f"   📍 {t['nakshatra']} Pada {t['pada']} | House *{h}* from Moon"
        )
    messages.append("\n".join(pos_lines))

    # ── MSG 3: Moon effect ──
    moon_today = transits.get("Moon", {})
    nak_health_note = NAKSHATRA_FLAVOUR.get(moon_today.get("nakshatra", ""), {}).get(
        "health", "The Moon's nakshatra colours the emotional and physical tone of the entire day."
    )
    messages.append(
        f"🌙 *MOON'S MESSAGE TODAY*\n{'─' * 30}\n\n"
        f"Moon in *{moon_today.get('sign', '—')} {moon_today.get('degree', 0):.1f}°*\n"
        f"Nakshatra: *{moon_today.get('nakshatra', '—')}* Pada {moon_today.get('pada', '—')}\n"
        f"House *{moon_h_today}* from your natal Moon ({moon_sign})\n\n"
        f"{'✅' if moon_benefic else '⚠️'} *{moon_effect_label}*\n\n"
        f"_{nak_health_note}_"
    )

    # ── MSG 4–14: One message per life area ──
    for topic in TOPIC_ORDER:
        verdict, para = _build_topic_paragraph(
            topic, transits, moon_sign, moon_nak,
            maha_lord, antar_lord,
            tithi["name"], tithi["paksha"], seed,
        )
        title = TOPIC_TITLES[topic]
        messages.append(f"{verdict} *{title}*\n{'─' * 30}\n{para}")

    # ── MSG 15: Do's & Don'ts ──
    dos, donts = [], []
    for pl in PLANET_LOOP:
        if pl not in transits: continue
        h = _house_from(moon_sign, transits[pl]["sign"])
        sig = DO_DONT_SIGNALS.get((pl, h))
        if not sig: continue
        do_txt, dont_txt = sig
        if do_txt:   dos.append(f"✅ {do_txt}")
        if dont_txt: donts.append(f"❌ {dont_txt}")

    dos.insert(0, f"🙏 {day_ritual}")
    dos.append("🕉️ Recite Gayatri Mantra 108 times at sunrise for clarity and divine protection.")
    donts.append(f"🔴 Avoid starting anything new during *Rahu Kaal: {RAHU_KAAL[weekday]}* (IST) — यह समय बहुत अशुभ माना जाता है।")
    if sade_active or dhaiya_active:
        donts.append("🪐 Avoid rash decisions — Saturn's transit demands patience and measured, careful action.")

    do_dont = (
        f"📋 *WHAT TO DO TODAY*\n{'─' * 30}\n"
        + "\n".join(dos)
        + f"\n\n🚫 *WHAT TO AVOID TODAY*\n{'─' * 30}\n"
        + "\n".join(donts)
    )
    messages.append(do_dont)

    # ── MSG 16: Auspicious Timings ──
    messages.append(
        f"⏰ *AUSPICIOUS TIMINGS (IST)*\n{'─' * 30}\n\n"
        f"  🟢 *Abhijit Muhurat:* {ABHIJIT_KAAL[weekday]}\n"
        f"     _Best muhurat of the day — ideal for any important new beginning_\n\n"
        f"  🟢 *Amrit Kaal:* {AMRIT_KAAL[weekday]}\n"
        f"     _Nectar period — highly auspicious for starting beneficial activities_\n\n"
        f"  🔴 *Rahu Kaal:* {RAHU_KAAL[weekday]}\n"
        f"     _Inauspicious — avoid starting anything new in this window_\n\n"
        f"  🟠 *Yamghant:* {YAMGHANT[weekday]}\n"
        f"     _Secondary inauspicious period — avoid important initiations_\n\n"
        f"_⚠️ राहु काल अपने आप में बहुत ज्यादा अशुभ समय माना जाता है। "
        f"यदि आप किसी भी नए काम की शुरुआत राहु काल में करते हैं तो आपको बहुत ज्यादा "
        f"समस्याओं का सामना करना पड़ता है। इसलिए राहु काल को जरूर जान लें।_"
    )

    # ── MSG 17: Footer ──
    messages.append(
        f"{'─' * 30}\n"
        f"🔱 *Hora Astrology · Daily Rashifal*\n"
        f"_Type /today to refresh · /start to regenerate Kundli_\n\n"
        f"🙏 *जय माता दी · राधे राधे · ॐ नमः शिवाय* 🙏"
    )

    return messages
