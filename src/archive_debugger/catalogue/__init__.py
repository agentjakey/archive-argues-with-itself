"""The whole collection, item by item: catalogue records (Phase 4 prep).

Every item in Internet Archive Canada's government publications collection is at least KNOWN to
this project: its catalogue record is fetched with the Internet Archive's bulk scrape API, kept as
fetched (raw pages, compressed, with checksums) and normalized into the registry. Fetching is
polite: an identified user agent with a contact address, at most two requests at a time, backoff,
everything cached, and a stop with a report on repeated 429 or 503 responses."""
