"""The philosophy layer: virtues, Franklin's method, quotes, practices.

Benjamin Franklin's 13 virtues are grouped under the four Stoic cardinal virtues so
his weekly-focus method can drive a Stoic practice. Each week puts one Franklin
virtue (and its Stoic parent) in focus; a full cycle is 13 weeks, four per year,
as Franklin describes in his Autobiography.
"""

from __future__ import annotations

import hashlib
from datetime import date as Date

VIRTUES = {
    "wisdom": {
        "name": "Wisdom",
        "greek": "Sophia",
        "summary": "Seeing things as they are; knowing what is and isn't up to you.",
        "color": "#2a78d6",
    },
    "courage": {
        "name": "Courage",
        "greek": "Andreia",
        "summary": "Acting rightly despite fear, discomfort, or fatigue.",
        "color": "#eb6834",
    },
    "justice": {
        "name": "Justice",
        "greek": "Dikaiosyne",
        "summary": "Treating others fairly and doing your duty to the common good.",
        "color": "#1baf7a",
    },
    "temperance": {
        "name": "Temperance",
        "greek": "Sophrosyne",
        "summary": "Self-control and moderation in appetite, speech, and emotion.",
        "color": "#eda100",
    },
}

# Franklin's precepts, as written in his Autobiography (spelling modernised).
FRANKLIN = [
    ("Temperance", "temperance", "Eat not to dullness; drink not to elevation."),
    ("Silence", "wisdom", "Speak not but what may benefit others or yourself; avoid trifling conversation."),
    ("Order", "wisdom", "Let all your things have their places; let each part of your business have its time."),
    ("Resolution", "courage", "Resolve to perform what you ought; perform without fail what you resolve."),
    ("Frugality", "temperance", "Make no expense but to do good to others or yourself; that is, waste nothing."),
    ("Industry", "courage", "Lose no time; be always employed in something useful; cut off all unnecessary actions."),
    ("Sincerity", "justice", "Use no hurtful deceit; think innocently and justly, and, if you speak, speak accordingly."),
    ("Justice", "justice", "Wrong none by doing injuries, or omitting the benefits that are your duty."),
    ("Moderation", "temperance", "Avoid extremes; forbear resenting injuries so much as you think they deserve."),
    ("Cleanliness", "temperance", "Tolerate no uncleanliness in body, clothes, or habitation."),
    ("Tranquility", "temperance", "Be not disturbed at trifles, or at accidents common or unavoidable."),
    ("Chastity", "temperance", "Treat intimacy with respect; never to the injury of your own or another's peace or reputation."),
    ("Humility", "justice", "Imitate Jesus and Socrates."),
]
FRANKLIN_BY_NAME = {name: (virtue, precept) for name, virtue, precept in FRANKLIN}

DEFAULT_BEHAVIORS = [
    # wisdom
    {"virtue": "wisdom", "franklin": "Order", "title": "Morning intention set",
     "question": "Did I decide in the morning what good I would do today?"},
    {"virtue": "wisdom", "franklin": "Order", "title": "Plan honoured",
     "question": "Did each part of my business have its time?"},
    {"virtue": "wisdom", "franklin": "Silence", "title": "Spoke with purpose",
     "question": "Did I avoid gossip, complaint, and trifling talk?"},
    {"virtue": "wisdom", "franklin": "Silence", "title": "Dichotomy of control",
     "question": "Did I let go of what was not up to me?"},
    # courage
    {"virtue": "courage", "franklin": "Resolution", "title": "Did the hard thing first",
     "question": "Did I do what I resolved, especially the thing I was avoiding?"},
    {"virtue": "courage", "franklin": "Industry", "title": "Trained the body",
     "question": "Did I move or train as my recovery allowed?"},
    {"virtue": "courage", "franklin": "Industry", "title": "No wasted hours",
     "question": "Did I avoid mindless scrolling and idle time?"},
    # justice
    {"virtue": "justice", "franklin": "Justice", "title": "Served someone",
     "question": "Did I do a concrete good for another person?"},
    {"virtue": "justice", "franklin": "Sincerity", "title": "Spoke truly",
     "question": "Was I honest and fair in what I said and did?"},
    {"virtue": "justice", "franklin": "Humility", "title": "Listened first",
     "question": "Did I listen to understand before I spoke?"},
    # temperance
    {"virtue": "temperance", "franklin": "Temperance", "title": "Ate and drank with moderation",
     "question": "Did I eat not to dullness and drink not to elevation?"},
    {"virtue": "temperance", "franklin": "Tranquility", "title": "Kept my composure",
     "question": "Was I undisturbed by trifles and the unavoidable?"},
    {"virtue": "temperance", "franklin": "Moderation", "title": "Protected sleep",
     "question": "Did I wind down on time and protect my rest?"},
    {"virtue": "temperance", "franklin": "Frugality", "title": "Spent with purpose",
     "question": "Did I avoid waste of money, attention, and energy?"},
]

# Each quote: text, author, source, virtue, practice (an actionable step for today).
QUOTES = [
    {"text": "Men are disturbed not by things, but by the opinions about things.",
     "author": "Epictetus", "source": "Enchiridion 5", "virtue": "wisdom",
     "practice": "When something irritates you today, name the judgement you added to the event."},
    {"text": "Some things are within our power, while others are not.",
     "author": "Epictetus", "source": "Enchiridion 1", "virtue": "wisdom",
     "practice": "Before each meeting, name one thing in it that is fully yours: your effort, your attention, your tone."},
    {"text": "Such as are thy habitual thoughts, such also will be the character of thy mind; for the soul is dyed by the thoughts.",
     "author": "Marcus Aurelius", "source": "Meditations 5.16", "virtue": "wisdom",
     "practice": "Notice what you read or watch first thing. Replace one input today with something worth becoming."},
    {"text": "If thou art pained by any external thing, it is not this thing that disturbs thee, but thy own judgement about it.",
     "author": "Marcus Aurelius", "source": "Meditations 8.47", "virtue": "wisdom",
     "practice": "Hold off on reacting to the next bad news for ten breaths. Then choose your response."},
    {"text": "Nothing, Lucilius, is ours, except time.",
     "author": "Seneca", "source": "Letters 1", "virtue": "wisdom",
     "practice": "Audit one hour of today's calendar: was it spent or invested?"},
    {"text": "It is not that we have a short time to live, but that we waste a lot of it.",
     "author": "Seneca", "source": "On the Shortness of Life 1", "virtue": "wisdom",
     "practice": "Pick the one block of the day you'll protect from interruption, and guard it."},
    {"text": "Since it is possible that thou mayest depart from life this very moment, regulate every act and thought accordingly.",
     "author": "Marcus Aurelius", "source": "Meditations 2.11", "virtue": "wisdom",
     "practice": "Memento mori: tell someone you care about what they mean to you."},
    {"text": "Let silence be the general rule, or let only what is necessary be said, and in few words.",
     "author": "Epictetus", "source": "Enchiridion 33", "virtue": "wisdom",
     "practice": "In your next conversation, speak half as much as usual and ask one more question."},
    {"text": "Men learn while they teach.",
     "author": "Seneca", "source": "Letters 7", "virtue": "wisdom",
     "practice": "Explain one idea you are learning to someone else today."},

    {"text": "The impediment to action advances action. What stands in the way becomes the way.",
     "author": "Marcus Aurelius", "source": "Meditations 5.20", "virtue": "courage",
     "practice": "Name today's biggest obstacle and find the action it makes possible."},
    {"text": "In the morning when thou risest unwillingly, let this thought be present: I am rising to the work of a human being.",
     "author": "Marcus Aurelius", "source": "Meditations 5.1", "virtue": "courage",
     "practice": "Get up at the first alarm. Do your hardest task before checking messages."},
    {"text": "There are more things likely to frighten us than there are to crush us; we suffer more often in imagination than in reality.",
     "author": "Seneca", "source": "Letters 13", "virtue": "courage",
     "practice": "Write the worst realistic outcome of what you fear today, then how you'd handle it."},
    {"text": "No longer talk at all about the kind of man that a good man ought to be, but be such.",
     "author": "Marcus Aurelius", "source": "Meditations 10.16", "virtue": "courage",
     "practice": "Skip the planning on one thing today and just do it."},
    {"text": "Every habit and faculty is maintained and increased by the corresponding actions.",
     "author": "Epictetus", "source": "Discourses 2.18", "virtue": "courage",
     "practice": "Do one rep of the habit you're building, even a small one, before noon."},
    {"text": "We will train both soul and body when we accustom ourselves to cold, heat, thirst, hunger, scarcity of food, and hardness of bed.",
     "author": "Musonius Rufus", "source": "Lectures 6", "virtue": "courage",
     "practice": "Voluntary discomfort: a cold shower finish, a fasted walk, or one set past where you'd stop."},
    {"text": "Practice yourself, for heaven's sake, in little things, and thence proceed to greater.",
     "author": "Epictetus", "source": "Discourses 1.18", "virtue": "courage",
     "practice": "Keep one small promise to yourself on purpose today, and notice that you kept it."},

    {"text": "Begin the morning by saying to thyself, I shall meet with the busybody, the ungrateful, arrogant, deceitful, envious, unsocial.",
     "author": "Marcus Aurelius", "source": "Meditations 2.1", "virtue": "justice",
     "practice": "Before your first meeting, decide how you'll respond kindly to the most difficult person you'll see."},
    {"text": "The best way of avenging thyself is not to become like the wrong doer.",
     "author": "Marcus Aurelius", "source": "Meditations 6.6", "virtue": "justice",
     "practice": "When someone is short with you, answer with patience. Once."},
    {"text": "When thou art offended with any man's shameless conduct, immediately ask thyself: Is it possible that shameless men should not be in the world?",
     "author": "Marcus Aurelius", "source": "Meditations 9.42", "virtue": "justice",
     "practice": "Expect friction. When it comes, treat it as weather, not a personal attack."},
    {"text": "What is not good for the swarm is not good for the bee.",
     "author": "Marcus Aurelius", "source": "Meditations 6.54", "virtue": "justice",
     "practice": "Do one useful thing today that nobody will thank you for."},
    {"text": "Never call yourself a philosopher, nor talk a great deal among the unlearned about theorems, but act conformably to them.",
     "author": "Epictetus", "source": "Enchiridion 46", "virtue": "justice",
     "practice": "Practice quietly. Help without mentioning it."},
    {"text": "Wherever there is a human being, there is an opportunity for a kindness.",
     "author": "Seneca", "source": "On the Happy Life 24", "virtue": "justice",
     "practice": "Find one person on today's calendar and leave them better off than you found them."},

    {"text": "Occupy thyself with few things, says the philosopher, if thou wouldst be tranquil.",
     "author": "Marcus Aurelius", "source": "Meditations 4.24", "virtue": "temperance",
     "practice": "Cut one non-essential task or commitment from today."},
    {"text": "Nowhere either with more quiet or more freedom from trouble does a man retire than into his own soul.",
     "author": "Marcus Aurelius", "source": "Meditations 4.3", "virtue": "temperance",
     "practice": "Take a five-minute retreat today: no phone, just breath and a look at the sky."},
    {"text": "It is not the man who has too little, but the man who craves more, that is poor.",
     "author": "Seneca", "source": "Letters 2", "virtue": "temperance",
     "practice": "Skip one purchase or one indulgence today and notice that you're fine."},
    {"text": "Set aside a certain number of days, during which you shall be content with the scantiest and cheapest fare, saying to yourself: Is this the condition that I feared?",
     "author": "Seneca", "source": "Letters 18", "virtue": "temperance",
     "practice": "Eat simply today: one plain meal, no snacks, no alcohol."},
    {"text": "Do not seek to have events happen as you want them to, but instead want them to happen as they do happen, and your life will go well.",
     "author": "Epictetus", "source": "Enchiridion 8", "virtue": "temperance",
     "practice": "Amor fati: when a plan breaks today, say 'good' and look for the use in it."},
    {"text": "No man is free who is not master of himself.",
     "author": "Epictetus", "source": "Fragments", "virtue": "temperance",
     "practice": "Pick one impulse to delay by ten minutes today: the snack, the scroll, the sharp reply."},
    {"text": "The perfection of moral character consists in this: in passing every day as the last, and in being neither violently excited, nor torpid, nor playing the hypocrite.",
     "author": "Marcus Aurelius", "source": "Meditations 7.69", "virtue": "temperance",
     "practice": "Keep an even keel: no highs chased, no slump indulged. Notice your state at noon and 4pm."},
]

# Body practices tuned to recovery state. Stoics trained the body as servant of the mind.
BODY_PRACTICE = {
    "push": {
        "title": "Train hard: you're recovered",
        "detail": "Readiness is high. Do your key session today: intervals, a long effort, or heavy strength. "
                  "Add voluntary discomfort if you like (Musonius). Courage is the virtue you're training.",
        "virtue": "courage",
    },
    "steady": {
        "title": "Steady work: zone 2 or technique",
        "detail": "Recovery is moderate. Choose an aerobic base session, mobility, or technique work. "
                  "Temperance means doing enough, not everything.",
        "virtue": "temperance",
    },
    "recover": {
        "title": "Recover on purpose",
        "detail": "Your body is asking for rest. Walk, stretch, nap if you can, and go to bed early. "
                  "Choosing rest over ego is temperance, and wisdom.",
        "virtue": "wisdom",
    },
    "unknown": {
        "title": "Move with intention",
        "detail": "No recovery data yet. Sync Garmin or log manually. Meanwhile a 30-minute walk is never wrong.",
        "virtue": "courage",
    },
}

FRANKLIN_MORNING = "What good shall I do this day?"
FRANKLIN_EVENING = "What good have I done to-day?"

# Week 0 of the Franklin cycle. Mondays from here count forward.
CYCLE_EPOCH = Date(2024, 1, 1)  # a Monday


def focus_for(day: Date) -> dict:
    """Franklin's method: one virtue in focus per week, 13-week cycle."""
    week_index = (day - CYCLE_EPOCH).days // 7
    name, virtue, precept = FRANKLIN[week_index % len(FRANKLIN)]
    return {
        "franklin": name,
        "precept": precept,
        "virtue": virtue,
        "virtue_name": VIRTUES[virtue]["name"],
        "week_of_cycle": week_index % len(FRANKLIN) + 1,
        "cycle_length": len(FRANKLIN),
    }


def _stable_index(seed: str, n: int) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16) % n


def quote_for(day: Date, virtue: str | None = None) -> dict:
    pool = [q for q in QUOTES if virtue is None or q["virtue"] == virtue] or QUOTES
    return pool[_stable_index(day.isoformat(), len(pool))]


def _clamp(v: float) -> float:
    return max(0.0, min(100.0, v))


def _mean(values: list[float]) -> float | None:
    values = [v for v in values if v is not None]
    return sum(values) / len(values) if values else None


def recovery_score(health: dict | None, hrv_baseline: float | None = None) -> float | None:
    """0-100 composite from whatever Garmin metrics exist for the day."""
    if not health:
        return None
    parts = []
    if health.get("training_readiness") is not None:
        parts.append(health["training_readiness"])
    if health.get("body_battery_high") is not None:
        parts.append(health["body_battery_high"])
    if health.get("stress_avg") is not None:
        parts.append(_clamp(100 - health["stress_avg"]))
    if health.get("hrv_ms") and hrv_baseline:
        # 100% of baseline -> 70, +/-15% swings the score across most of the range
        parts.append(_clamp(70 + (health["hrv_ms"] / hrv_baseline - 1) * 200))
    m = _mean(parts)
    return round(m, 1) if m is not None else None


def rest_score(health: dict | None) -> float | None:
    if not health:
        return None
    if health.get("sleep_score") is not None:
        return float(health["sleep_score"])
    if health.get("sleep_seconds"):
        return round(_clamp(health["sleep_seconds"] / (8 * 3600) * 100), 1)
    return None


def exercise_score(health: dict | None, activities: list[dict], target_minutes: int = 30) -> float | None:
    minutes = None
    if health and health.get("intensity_minutes") is not None:
        minutes = health["intensity_minutes"]
    act_minutes = sum((a.get("duration_s") or 0) for a in activities) / 60
    if act_minutes:
        minutes = max(minutes or 0, act_minutes)
    if minutes is None:
        if health and health.get("steps") is not None:
            return round(_clamp(health["steps"] / 10000 * 100), 1)
        return None
    return round(_clamp(minutes / target_minutes * 100), 1)


def philosophy_score(journal: dict | None, evaluated: int, total_behaviors: int) -> float:
    score = 0.0
    if journal:
        if (journal.get("morning_intention") or "").strip():
            score += 30
        if (journal.get("evening_review") or "").strip():
            score += 30
        if journal.get("practice_done"):
            score += 15
    if total_behaviors:
        score += 25 * min(1.0, evaluated / total_behaviors)
    return round(score, 1)


def readiness_state(recovery: float | None) -> str:
    if recovery is None:
        return "unknown"
    if recovery >= 70:
        return "push"
    if recovery >= 45:
        return "steady"
    return "recover"


def daily_insight(day: Date, health: dict | None, hrv_baseline: float | None,
                  weakest_virtue: str | None) -> dict:
    """Combine the week's focus, the body's state, and recent lapses into today's guidance."""
    focus = focus_for(day)
    recovery = recovery_score(health, hrv_baseline)
    state = readiness_state(recovery)

    # On low-recovery days temperance outranks the weekly focus: rest is the virtuous act.
    quote_virtue = focus["virtue"]
    if state == "recover":
        quote_virtue = "temperance"
    quote = quote_for(day, quote_virtue)

    recommendations = [
        {"kind": "philosophy", "virtue": quote["virtue"], "title": "Today's practice",
         "detail": quote["practice"]},
        {"kind": "body", **BODY_PRACTICE[state]},
        {"kind": "franklin", "virtue": focus["virtue"],
         "title": f"Week's focus: {focus['franklin']}",
         "detail": focus["precept"]},
    ]
    if weakest_virtue and weakest_virtue != focus["virtue"]:
        recommendations.append({
            "kind": "growth", "virtue": weakest_virtue,
            "title": f"Watch your {VIRTUES[weakest_virtue]['name'].lower()}",
            "detail": f"{VIRTUES[weakest_virtue]['name']} has had the most lapses over the last two weeks. "
                      f"Look for one moment today to practise it on purpose.",
        })
    if health and health.get("sleep_seconds") and health["sleep_seconds"] < 6.5 * 3600:
        recommendations.append({
            "kind": "rest", "virtue": "temperance", "title": "Protect tonight's sleep",
            "detail": "You slept under 6.5 hours. Set a wind-down alarm and keep screens out of the bedroom.",
        })

    return {
        "date": day.isoformat(),
        "focus": focus,
        "quote": quote,
        "recovery": recovery,
        "state": state,
        "recommendations": recommendations,
        "morning_question": FRANKLIN_MORNING,
        "evening_question": FRANKLIN_EVENING,
    }
