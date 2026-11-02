# Design research for the exhibit kiosk

This is the reading behind the kiosk redesign. The kiosk stands in a library, people walk up to it
cold, and most of them will give it a few minutes at most. Some will read every word. Some will
stand two or three metres back while a friend plays. The notes below are what we read about
designing for that, what each source actually says, and the rule each finding turned into. The
rules are numbered R1 to R16 and the kiosk code follows them; the table at the end maps each
finding to its rule.

Every source here was fetched on 2026-11-02. Where a source could not be fetched, or did not say
what we hoped it would say, that is written down too.

## Museum interactives

### The 3-30-3 rule, and where it really comes from

Exhibit designers talk about a "3-30-3" pattern: about 3 seconds for a passer-by to decide whether
to stop, about 30 seconds for the visitor who stops to get the main idea, and about 3 minutes for
the one who stays to go deeper. We looked for who coined it and could not find a primary source.
Searches turned up marketing and trade-show versions of the same idea, and one site that describes
a "3-30-3 rule" for first impressions (network9.biz) refused our connection, so we do not cite it.
We treat 3-30-3 as a working heuristic of the trade, not a research finding.

What does have a solid source is the idea underneath it. The Smithsonian's
[Guide to Interpretive Writing for Exhibitions](https://exhibits.si.edu/wp-content/uploads/2021/09/SI-Guide-to-Interpretive-Writing-for-Exhibitions.pdf)
asks writers to "Make content pathways for a variety of visitors": "Some visitors want just the
big idea, so give them a heading or subheading that encapsulates the main point of the label. Some
visitors want to skim, so give them a summary sentence in addition to the heading. Other visitors
want to know more, and more extensive labels will satisfy them." It also reports, citing Beverly
Serrell, that "the average visit to a 2,000-square-foot exhibition lasts just five to ten minutes",
and that "Most visitors 'sample' content in random and non-sequential ways." Its sentence rules are
plain: "Put a single idea in each sentence", and keep sentences "to 15 to 20 words or fewer and
never more than 25 words."

The St. Olaf art department's notes on label writing
([wp.stolaf.edu/art/?p=7469](https://wp.stolaf.edu/art/?p=7469)) give the usual word ranges (titles
1 to 7 words, introductory labels 20 to 125, object labels 75 to 150) and quote Serrell that "The
best titles will arouse interest and curiosity".

What we took: three layers on every screen. The 3-second layer is one line and one button. The
30-second layer is the round itself: one question, the choices, the answer. The 3-minute layer is
the page text and "how we know", there for the visitor who stays, behind a button so it never
crowds the first two. A whole visit should fit the five-to-ten-minute window the Smithsonian
reports for a whole exhibition, so ours aims at three to five minutes and then ends cleanly. Copy
follows the sentence rules above. (R5, R6, and the copy rules under R13.)

### Ten-foot UI

Microsoft's [Designing for Xbox and TV](https://learn.microsoft.com/en-us/windows/apps/design/devices/designing-for-tv)
names the "10-foot experience" because "the user is generally sitting approximately 10 feet away
from the screen." Its first principle is "Simple": "Resolution and viewing distance can make it
difficult for people to process too much information. Try to keep your design clean, reduced to the
simplest possible components. The amount of information displayed on a TV should be comparable to
what you'd see on a mobile phone, rather than on a desktop." It asks designers to "Make the focus
clear and unmistakable" and to "Give people the shortest path to what they want to do". It warns
against tooltips, which on a remote appear on focus and "could be distracting", and against colour
alone: "If your app relies on subtle differences in color to differentiate parts of the UI, colors
could blend together and users could get confused." It also says to keep essential text and
controls out of the outer 5 percent of the screen.

Android's [Design for TV](https://developer.android.com/design/ui/tv/guides/foundations/design-for-tv)
puts the same distance in metres: "the average distance between a TV and its viewers is 3 meters
(10 feet)", so "it is important to make sure that text and other elements are large enough to be
seen from a distance or limit the amount of text and reading on TV screens." On input: "most TVs
rely on d-pad (up, down, left, right, select buttons on the remote) to navigate the UI. TV UI must
provide instant and distinct feedback when buttons are pressed." It also notes that "TV is a
communal device", which for us is the group of people standing behind the player.

What we took: phone-sized information density on a wall-sized screen (R1). A focus ring that can be
seen from across the room (R15). Everything reachable with arrows, Tab and Enter, because the
exhibit's USB knob is effectively a d-pad with a select button (R7, R15). Nothing that depends on
hover. A safe margin around the edge of the screen. Colour never carries meaning on its own (R4).

### Smithsonian Guidelines for Accessible Exhibition Design

The [Smithsonian Guidelines for Accessible Exhibition Design](https://www.sifacilities.si.edu/sites/default/files/Files/Accessibility/accessible-exhibition-design1.pdf)
were written for physical galleries, but most of the interactive and label rules carry straight
over to a screen.

Type size. "Select type size appropriate to the viewing distance." Its Fig. 12 (credited to Parks
Canada) gives minimum x-heights by probable viewing distance: 9 mm at 1 m, 19 mm at 2 m and 28 mm
at 3 m. "Minimum type size, at even the shortest distance, is an x-height of 4.5 mm (3/16 in.)".
It adds that "People who have low vision will need larger type than other visitors at every
distance", and that leading "should be at least 20 percent greater than the font size used."

We worked that through for a 55-inch 1920x1080 screen, where one pixel is about 0.63 mm. Assuming
a book serif's x-height of a bit under half the font size (an assumption; we did not measure
Crimson Text's), 32 px body type has an x-height near 9 mm, which is the 1 m row of the table. A
64 px heading is near 17 mm, just short of the 2 m row. So the brief's floor of 32 px body and 64 px
headings is right for the person at the controls, but the one thing a watcher two or three metres
back needs to read (the year on the dial, the question, the verdict) has to be much bigger than the
floor: we set those at 96 px and up at 1920x1080. On a smaller screen the same CSS gives smaller
millimetres, so the hardware notes should say 55 inches or larger.

Contrast and surface. "Provide high contrast between text and background." The guidelines ask for
"A 70% light reflectance value contrast", note that "dark on light works marginally better than
light on dark for headlines", and that "Lighter type weight and greater letter spacing is required
when type is reversed out of the background". "Print only on a solid background": "Overprinting
(type on an imaged background) is unreadable for people with low vision". Labels "should be printed
on eggshell, matte, or other non-glare surfaces", and interactives should "Eliminate glare on the
interactive's instructional surfaces", "a monitor screen or a plexiglass protective panel" named
directly. We use the WCAG measure rather than reflectance percentages, because it can be computed
from the colours in the stylesheet (see R3 below), and we keep text on flat fills, never on the
page images or on a texture.

Interactives. "Instructions for proper use of interactives must be accessible to all visitors":
"Write instructions for interactives in a short-sentence, step-by-step format", and "Instructions
are more effective for people with cognitive disabilities if participant action is required after
each direction rather than after a string of directions." Touch areas should be "in predictable
locations" and "at least 75 mm (3 in.) in diameter". Controls must "be fully operable with only one
hand" and "require no tight grasping, pinching, or twisting of the wrist". For a forward approach in
a wheelchair, controls "can be no higher than 1220 mm (48 in.) and no lower than 380 mm (15 in.)
above the floor".

Sound. Interactives with soundtracks "must be either open or closed captioned"; "Interactives and
audiovisuals that do not have soundtracks must carry labels stating that fact"; visitors should get
"visitor-operated volume controls"; and designers should "Prevent sound from overlapping between
interactive areas."

What we took (R16): one step per screen, with the visitor doing something after each instruction.
The main buttons sit in the same place on every screen, along the bottom, and are large: 75 mm on a
55-inch screen is about 118 px, so the main action buttons are at least that tall at 1920x1080 and
no control anywhere is below 64 px (R4). The knob is the one-handed control and needs no grip
beyond turning; the touch screen does everything the knob does. The dial's click is the only sound,
it says nothing that is not also on screen, it is off by default, and the toggle is on screen (R7).
Flat solid colours under all text. The hardware notes keep the reach heights and ask for a matte
screen or anti-glare film.

## Games that do one thing well

We looked at these for patterns only. Nothing in the kiosk copies their names, art, layouts or
code.

### A shared screen and a private choice (Jackbox, Kahoot)

Jackbox's [how to play page](https://www.jackboxgames.com/how-to-play) says that "the host screen
should be visible to the whole room" and that "Players can join the lobby room by visiting
jackbox.tv using the room code on the host's screen", under the heading "Use phones as
controllers". [Wikipedia](https://en.wikipedia.org/wiki/The_Jackbox_Party_Pack) adds that games
are "generally limited to 4-8 active players" and that latecomers "become audience participants",
where "the audience may also participate by voting as a group".

Kahoot puts the question on the big screen and the answering in hand: "Questions and answer
alternatives will be displayed on the shared screen, while students answer on their devices"
([how to play](https://kahoot.com/how-to-play-kahoot/)). Its
[getting-started post](https://kahoot.com/blog/2019/03/04/how-to-get-started-with-kahoot/) explains
the link between the two: "Each answer option on the shared screen is inside a box with a specific
color and shape" that "matches the boxes displayed on the players' screen." Its
[accessibility page](https://kahoot.com/accessibility/) lists a high-contrast theme and "Full
keyboard navigation support".

What we took: the big screen is for the room, the choice is private until everyone has chosen, and
each choice has a shape as well as a colour so it can be named and found without colour (R4, R9).
What we did not take: phones. A library kiosk has no network to rely on and must collect nothing,
so group play passes the one screen from hand to hand and each player picks in secret (R9).

### Year guessing and timelines (TimeGuessr, Wikitrivia)

[Gigazine's write-up of TimeGuessr](https://gigazine.net/gsc_news/en/20230821-timeguessr)
describes a photo, a map and a year slider: "place the pin, move the slide to match '1944', and
click 'Make guess'." The reveal shows the real year and place and scores each guess, up to 5,000
points for the year and 5,000 for the place. There are five photos, and after them "the total score
of all 5 questions will be displayed."

[Wikitrivia](https://en.wikipedia.org/wiki/Wikitrivia) has players "put the event in the correct
place in the timeline (between other cards)"; "Placing a card in the wrong position loses a life,
and the game ends once three lives are lost." It is built from Wikipedia and Wikidata, and its
author "encourages players to report incorrect cards".

What we took: a short fixed run of cards with a total at the end, a single control for the year
that is always in the same place, and points by closeness so a near miss still feels like progress
(R6, R11). We kept points proportional to distance, which When Was This? already does. We did not
take lives or a fail state; a visitor at an exhibit should never be thrown out.

### Document inspection (Papers, Please)

On [Wikipedia](https://en.wikipedia.org/wiki/Papers,_Please) the core of the game is that "the
player must review the documents of arrivals", that "the player is given specific rules on what
documentation is required and conditions to allow entry", and that "If discrepancies are discovered,
the player may interrogate the applicant". The fan wiki pages that describe its inspection mode in
detail (papersplease.fandom.com) returned an error when we fetched them, so we do not quote them.

That is exactly what Same or Not? asks: two documents side by side and a short list of things that
must match before they can be compared. What we took: the two claims sit side by side, with a fixed
checklist under them (period, place, population, program, measure), and the reveal fills in that
checklist row by row with "same", "differs" or "unclear", each as a word and a symbol (R10). We
took none of its setting, tone or art.

### Reveal pacing (GeoGuessr)

On [Wikipedia](https://en.wikipedia.org/wiki/GeoGuessr) a game "consists of five rounds", the
player places a pin, and "receives a score of up to 5,000 points depending on how accurate their
guess was". A student review in [The Northern Light](https://www.thenorthernlight.org/stories/geoguessr-a-fun-and-easy-way-to-break-winter-boredom)
puts the reveal simply: "The game will then show the true location and give the player points based
on how close their guess was." A strategy wiki page that describes the result screen in more detail
returned 403, so we do not quote it.

What we took: the reveal is the reward, so it is staged. First your guess, then the truth beside it
on the same line, then the distance and points, then the evidence (R8, R11). Each step waits about
0.8 s. With reduced motion, everything appears at once and nothing slides.

## Agora: the owner's own game

[Agora](https://github.com/agentjakey/agora) is Jacob Ortiz's multiplayer philosophy game (MIT,
read at commit 654bf8f). It is his code, so we reuse its look and two of its patterns directly. Its
[README](https://github.com/agentjakey/agora/blob/main/README.md) describes a round as: "everyone
votes at the same time", then "the room reveals - 7 people chose one thing, 3 chose yours", then
"now you have to explain yourself". "No points. No leaderboard. No wrong answers. Just the
conversation." At the end comes "a full chronicle of every question, every split".

What we took:

- The palette from [frontend/src/index.css](https://github.com/agentjakey/agora/blob/main/frontend/src/index.css):
  near-black ground `#0e0c09`, surface `#1a1710`, border `#3a3320`, parchment text `#e8dfc0`,
  secondary text `#9a8f72`, dark gold `#b8860b` with hover `#d4a017`. The secondary text and the
  gold are too dark on that ground for AAA body text, so the kiosk lightens them until they measure
  7:1 or better, keeping the hue (R3).
- The type: Cinzel for display and Crimson Text for body. Agora loads both from the Google Fonts
  CDN; the kiosk self-hosts them instead so it works with no network. Both are SIL Open Font
  Licence fonts in the Google Fonts library (Cinzel by Natanael Gama,
  [METADATA](https://raw.githubusercontent.com/google/fonts/main/ofl/cinzel/METADATA.pb); Crimson
  Text by Sebastian Kosch,
  [METADATA](https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/METADATA.pb)), and
  their licence files ship with the kiosk (R14).
- The restraint: near-square corners (`border-radius: 1px`), thin rules, no shadows, no badges, no
  emoji, uppercase letter-spaced Cinzel on buttons (R14).
- The split-bar reveal from [frontend/src/screens/Reveal.jsx](https://github.com/agentjakey/agora/blob/main/frontend/src/screens/Reveal.jsx)
  and [Reveal.css](https://github.com/agentjakey/agora/blob/main/frontend/src/screens/Reveal.css):
  the bar starts even, then settles to the real split ("after 100ms, animate bar to actual split
  (1.5s ease-out)"), the numbers fade in at 1.6 s, the framing at 2.1 s and the controls at 2.5 s.
  Agora's bar has two parts; ours has one part per choice, each with its letter, shape and count in
  words, because colour cannot carry it (R9).
- The chronicle from [frontend/src/screens/Summary.jsx](https://github.com/agentjakey/agora/blob/main/frontend/src/screens/Summary.jsx):
  a closing list of every question with its split. Ours lists each round, what the visitor said and
  what the record says, with the honesty label and the printable evidence card (R12).

What we did not take: per-player phones and the WebSocket room (the kiosk is offline and keeps
nothing), the AI-generated questions (every round here comes from the checked deck), the
"philosophical profile" (we do not profile visitors), and the copy-to-clipboard button. The faint
noise texture over the background is optional and off, because the Smithsonian guidelines ask for
text on a solid ground.

## Web standards we measured against

WCAG 2.2 success criterion 1.4.6, Contrast (Enhanced), Level AAA
([Understanding 1.4.6](https://www.w3.org/WAI/WCAG22/Understanding/contrast-enhanced.html)): "a
contrast ratio of at least 7:1", except that "Large-scale text and images of large-scale text have a
contrast ratio of at least 4.5:1", large scale meaning "at least 18 point or 14 point bold". Every
size on the kiosk is large scale by that definition, but we hold body text to 7:1 anyway and use
4.5:1 only for headings and the big numerals (R3). The ratios are computed from the stylesheet's
colours and written into the redesign report, not assumed.

Success criterion 2.5.5, Target Size (Enhanced)
([Understanding 2.5.5](https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html)): "at
least 44 by 44 CSS pixels". The kiosk's floor of 64 px is above that, and the main actions follow
the Smithsonian's 75 mm (R4).

MDN on [prefers-reduced-motion](https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion):
it detects "if a user has enabled a setting on their device to minimize the amount of non-essential
motion." The kiosk honours it and also has its own on-screen switch, since a kiosk visitor cannot
change the device setting (R8).

## The rules

- R1. One dominant element per screen: the thing to look at is the biggest thing there.
- R2. Type: body at least 32 px and headings at least 64 px at 1920x1080, scaling with the screen
  (twice that at 3840x2160) and with a readable floor on a phone. The one thing a watcher at 2 to 3
  m must read (the year, the question, the verdict) is 96 px or more at 1920x1080. One exception:
  a Time Dial question is a whole sentence, so it is set at 72 px to stay on two lines.
- R3. WCAG AAA contrast, measured: 7:1 for body text, 4.5:1 for large text.
- R4. Choices are told apart by shape, letter and word, never colour alone. Touch targets are at
  least 64 px; main actions at least 118 px tall (75 mm on a 55-inch screen).
- R5. 3-30-3 as layers: the attract screen reads in 3 seconds (one line, one button); a round takes
  about 30 to 60 seconds; the page text and "how we know" wait behind a button for the visitor who
  stays.
- R6. One tap from the attract loop into play. A 3 to 5 minute arc: two When Was This? cards, two
  Same or Not? rounds and one Time Dial question, then the chronicle and the printable evidence
  card.
- R7. A year dial that feels physical: a tape with a tick for every year and a labelled tick for
  every decade moving under a fixed needle; detents, so it always settles on a whole year; drag,
  wheel, arrow keys and the USB knob all turn it; a click sound, off by default behind an on-screen
  toggle.
- R8. Paced reveals: your guess, then the answer, then the lines that settle it, then how we know,
  about 0.8 s apart. With reduced motion everything appears at once and nothing slides.
- R9. Group mode for Same or Not?: each player picks in secret on the one screen and passes it on;
  then the split-bar reveal, with the count for each choice in words. No phones, no network, nothing
  kept.
- R10. Same or Not? is a document inspection: the two claims side by side over a checklist (period,
  place, population, program, measure) that the reveal fills with same, differs or unclear, as words
  and symbols.
- R11. When Was This? shows your guess and the true year on one timeline, with the distance and the
  points.
- R12. The chronicle: a closing list of each round, what the visitor said and what the record says,
  held in memory only and wiped on reset, with the evidence card to print.
- R13. Honesty labels on every reveal and on the chronicle: "Checked by AI against the pages; human
  review pending", and in French a note that the French was drafted by AI and awaits review. Copy is
  short, plain and human: one idea a sentence, under 20 words where possible.
- R14. The Agora look (palette, Cinzel and Crimson Text, square corners, no shadows, badges or
  emoji), with the fonts self-hosted and their licences shipped.
- R15. Ten-foot rules: few items, a focus ring visible across the room, everything reachable by
  arrows, Tab and Enter (the knob is a d-pad with a select), nothing that depends on hover, nothing
  essential in the outer edge of the screen.
- R16. From the Smithsonian guidelines: one step and one action at a time; main controls in the same
  place on every screen; one-handed operation; text only on flat solid colour; sound optional, never
  the only carrier of anything, and under the visitor's control; a matte screen and accessible reach
  heights in the hardware notes.

## What we measured

All on 2026-11-02, against the kiosk as the kiosk serves it (the assembled release, installed and
served by `exhibit/kiosk/serve.py`).

Contrast, from the colour tokens in `exhibit/app/src/styles.css` (`npm run contrast` in
`exhibit/app` recomputes these and fails if any pair drops under its bar):

| Pair | Ratio | Bar | Used for |
|---|---|---|---|
| parchment `#e8dfc0` on ground `#0e0c09` | 14.65:1 | 7:1 | body text, headings, page text |
| parchment on surface `#1a1710` | 13.41:1 | 7:1 | claims, choices, page panels |
| parchment on raised surface `#242016` | 12.18:1 | 7:1 | pressed toggles, dial buttons |
| secondary `#c2b791` on ground | 9.74:1 | 7:1 | notes, review status |
| secondary on surface | 8.92:1 | 7:1 | choice help |
| secondary on raised surface | 8.10:1 | 7:1 | secondary text on raised panels |
| gold `#d4a017` on ground | 8.22:1 | 7:1 | kickers, verdicts, the dial's year |
| gold on surface | 7.53:1 | 7:1 | panel labels, checklist marks |
| ground on gold | 8.22:1 | 7:1 | main buttons, marked quotes |
| ground on parchment | 14.65:1 | 7:1 | the evidence card |
| gold on raised surface | 6.84:1 | 4.5:1 | large text only |
| edge `#8a7f5f` on ground / on surface | 4.91:1 / 4.50:1 | 3:1 | control edges |

Agora's own secondary `#9a8f72` measures 6.09:1 on the ground and its gold `#b8860b` 6.00:1, both
short of 7:1 for body text, which is why the kiosk lightens them.

axe-core (through `@axe-core/playwright`), with the WCAG 2.0, 2.1 and 2.2 A and AA rules plus the
AAA contrast rule (`color-contrast-enhanced`), on 16 screens at each of 1920x1080, 3840x2160 and
390x844: 48 runs, no violations of any impact. axe also reports "incomplete" checks it cannot decide
(for example text over a pattern); those were not reviewed one by one.

A whole visit, attract screen to chronicle, completed from the keyboard alone at 1920x1080 and at
3840x2160. A recorded visit at 1920x1080 took 58 seconds of scripted play; a real visitor reading
the pages takes longer, which is the point of the 3 to 5 minute arc, but nobody has timed real
visitors yet.

What these numbers do not say: nobody has played the redesign at a real kiosk, at 2 to 3 m, with a
real knob, or with a screen reader. Those wait for the playtest (docs/exhibit/playtest.md).

## Finding to rule

| Finding | Source | Rule |
|---|---|---|
| Information on a TV should be comparable to a phone, not a desktop | Microsoft, Designing for Xbox and TV | R1, R15 |
| Text large enough to read at 3 m, or less text | Android, Design for TV | R1, R2 |
| x-height by viewing distance: 9 mm at 1 m, 19 mm at 2 m, 28 mm at 3 m | Smithsonian SGAED, Fig. 12 | R2 |
| High contrast between text and background; no text over images | Smithsonian SGAED | R3, R16 |
| 7:1, and 4.5:1 for large text | WCAG 2.2, 1.4.6 | R3 |
| Do not rely on subtle colour differences | Microsoft, Designing for Xbox and TV | R4 |
| Answers carry a colour and a shape that match across screens | Kahoot | R4, R9 |
| Touch areas at least 75 mm; targets at least 44 CSS px | Smithsonian SGAED; WCAG 2.2, 2.5.5 | R4 |
| Content pathways: heading, summary, then more for those who want it | Smithsonian interpretive writing guide | R5 |
| Average visit to a whole exhibition is five to ten minutes | Smithsonian interpretive writing guide, citing Serrell | R6 |
| Shortest path to what people want to do | Microsoft, Designing for Xbox and TV | R6 |
| D-pad navigation with instant, distinct feedback | Android, Design for TV | R7, R15 |
| One year control, points by closeness, a short fixed run with a total | TimeGuessr (Gigazine) | R6, R7, R11 |
| Placing events on a timeline | Wikitrivia | R11 |
| Show the truth, then points by closeness | GeoGuessr (Wikipedia, The Northern Light) | R8, R11 |
| Staged reveal: bar, then numbers, then framing, then controls | Agora Reveal.jsx | R8, R9 |
| Shared screen for the room, private choices | Jackbox, Kahoot | R9 |
| Everyone votes at once, then the room sees the split | Agora README | R9 |
| Review documents against a fixed set of rules | Papers, Please (Wikipedia) | R10 |
| A closing chronicle of every question and split | Agora Summary.jsx | R12 |
| One idea a sentence; 15 to 20 words or fewer | Smithsonian interpretive writing guide | R13 |
| Palette, type and restraint | Agora index.css | R14 |
| Users can ask for less motion | MDN, prefers-reduced-motion | R8 |
| Clear, unmistakable focus; no tooltips | Microsoft, Designing for Xbox and TV | R15 |
| Step-action-step instructions; one-handed controls; captioned or optional sound; matte surfaces; reach heights | Smithsonian SGAED | R16 |

## Sources

All fetched 2026-11-02.

- Smithsonian Accessibility Program, Smithsonian Guidelines for Accessible Exhibition Design.
  https://www.sifacilities.si.edu/sites/default/files/Files/Accessibility/accessible-exhibition-design1.pdf
- Smithsonian Institution, Guide to Interpretive Writing for Exhibitions.
  https://exhibits.si.edu/wp-content/uploads/2021/09/SI-Guide-to-Interpretive-Writing-for-Exhibitions.pdf
- St. Olaf College Art Department, Interpretive Writing for the Exhibition. https://wp.stolaf.edu/art/?p=7469
- Microsoft Learn, Designing for Xbox and TV.
  https://learn.microsoft.com/en-us/windows/apps/design/devices/designing-for-tv
- Android Developers, Design for TV. https://developer.android.com/design/ui/tv/guides/foundations/design-for-tv
- W3C, Understanding SC 1.4.6 Contrast (Enhanced). https://www.w3.org/WAI/WCAG22/Understanding/contrast-enhanced.html
- W3C, Understanding SC 2.5.5 Target Size (Enhanced). https://www.w3.org/WAI/WCAG22/Understanding/target-size-enhanced.html
- MDN, prefers-reduced-motion. https://developer.mozilla.org/en-US/docs/Web/CSS/@media/prefers-reduced-motion
- Jackbox Games, How to play. https://www.jackboxgames.com/how-to-play
- Wikipedia, The Jackbox Party Pack. https://en.wikipedia.org/wiki/The_Jackbox_Party_Pack
- Kahoot!, How to play. https://kahoot.com/how-to-play-kahoot/
- Kahoot!, How to get started with Kahoot! https://kahoot.com/blog/2019/03/04/how-to-get-started-with-kahoot/
- Kahoot!, Accessibility. https://kahoot.com/accessibility/
- Gigazine, TimeGuessr write-up. https://gigazine.net/gsc_news/en/20230821-timeguessr
- Wikipedia, Wikitrivia. https://en.wikipedia.org/wiki/Wikitrivia
- Wikipedia, Papers, Please. https://en.wikipedia.org/wiki/Papers,_Please
- Wikipedia, GeoGuessr. https://en.wikipedia.org/wiki/GeoGuessr
- The Northern Light, GeoGuessr review.
  https://www.thenorthernlight.org/stories/geoguessr-a-fun-and-easy-way-to-break-winter-boredom
- Google Fonts metadata for Cinzel and Crimson Text.
  https://raw.githubusercontent.com/google/fonts/main/ofl/cinzel/METADATA.pb and
  https://raw.githubusercontent.com/google/fonts/main/ofl/crimsontext/METADATA.pb
- Jacob Ortiz, Agora (MIT), commit 654bf8f. https://github.com/agentjakey/agora

Tried and not used: network9.biz (connection refused), papersplease.fandom.com (HTTP 402),
strategywiki.org (HTTP 403), and a Taylor and Francis article on how visitors read art-museum labels
(tandfonline.com, HTTP 403).
