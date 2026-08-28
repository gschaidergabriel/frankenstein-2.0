#!/usr/bin/env python3
"""Inject a bounded Trigger-6 regression into AgentSight's exact pinned http_parser.rs.

Research-only fixture. It creates no real effects and does not modify the candidate repository.
The caller operates on a disposable checkout pinned by the workflow.
"""
from pathlib import Path
import sys

path = Path(sys.argv[1])
text = path.read_text(encoding="utf-8")
needle = "pub fn parse_http_message(data: &str) -> Option<HTTPMessage>"
if needle not in text:
    raise SystemExit("expected AgentSight parser identity not found")

fixture = r'''

#[cfg(test)]
mod trigger6_http1_content_length_e3 {
    use super::*;

    #[test]
    fn trigger6_http1_content_length_partial_acceptance() {
        let input = "POST /v1/messages HTTP/1.1\r\nHost: example.invalid\r\nContent-Length: 10\r\nContent-Type: application/json\r\n\r\nabc";
        let parsed = HTTPParser::parse_http_message(input)
            .expect("current parser rejected the intentionally incomplete message");
        let declared: usize = parsed
            .headers
            .get("content-length")
            .expect("content-length missing")
            .parse()
            .expect("content-length not numeric");
        let available = parsed.body.as_deref().unwrap_or("").len();
        eprintln!("TRIGGER6_E3 declared_content_length={declared} available_body_length={available}");
        assert_eq!(declared, 10);
        assert_eq!(available, 3);
        assert!(available < declared, "fixture must remain intentionally incomplete");
    }
}
'''

if "mod trigger6_http1_content_length_e3" in text:
    raise SystemExit("fixture already present")
path.write_text(text + fixture, encoding="utf-8")
print(path)
