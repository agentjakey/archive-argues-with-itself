"""The library exhibit's deck builder (docs/formats/exhibit-deck.md).

A deck is a release of game rounds built from real pages: Same or Not?, When Was This?, the Time
Dial and Gap Hunt. Every round names its pages by item and leaf, carries the page text it quotes,
and records how each date was verified, who drafted and who reviewed it, and its status. The
builder refuses a round whose page does not resolve, whose quote is not on the page, whose date is
not verified, or that touches an excluded care topic. No collection is named in code: rounds come
from the collections in config/exhibit.toml, read through the audit's collection configs."""
