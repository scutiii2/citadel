# capabilities/web_research/

Search the web, read a page, list a site's pages and crawl a site - four tools. Each tool tries several engines in order and uses the first that answers.

## Tools

| Tool | Purpose | Connection |
| --- | --- | --- |
| `tool_web_search` | Search the web; returns titles, addresses and snippets. | Tavily or Firecrawl |
| `tool_web_readPage` | Read the text of one web page. | Tavily, Firecrawl, Firecrawl Local or Scrapy |
| `tool_web_map` | List the pages found on a site. | Tavily, Firecrawl, Firecrawl Local or Scrapy |
| `tool_web_crawl` | Crawl a site and return the text of its pages. | Tavily, Firecrawl, Firecrawl Local or Scrapy |

## Slash commands

| Tool | Slash command | Parameters |
| --- | --- | --- |
| `tool_web_search` | `/web search` | <ul><li>`query` - required. What to search for.</li><li>`max_results` - optional, default `5`. How many results (1 to 10).</li><li>`topic` - optional, default `general`. `news` for recent events.</li></ul> |
| `tool_web_readPage` | `/web read` | <ul><li>`url` - required. Full http:// or https:// address.</li></ul> |
| `tool_web_map` | `/web map` | <ul><li>`url` - required. Full http:// or https:// address of the site or section.</li><li>`limit` - optional, default `100`. How many pages to list (1 to 500).</li></ul> |
| `tool_web_crawl` | `/web crawl` | <ul><li>`url` - required. Full http:// or https:// address where the crawl starts.</li><li>`limit` - optional, default `10`. How many pages to read (1 to 25).</li></ul> |

## Typical workflow

| Sequence | Tool | Explanation |
| --- | --- | --- |
| 1 | `tool_web_search` | Find candidate pages. |
| 2 | `tool_web_readPage` | Read the best one or two pages, then answer and cite their addresses. |
| 3 | `tool_web_map` | To work through one site, list its pages and pick. |
| 4 | `tool_web_crawl` | Crawl from a starting address when many pages are needed. |

## Engines and order

| Order | Engine | Search | Needs |
| --- | --- | --- | --- |
| 1 | [Tavily](https://tavily.com) | yes | Tavily API key |
| 2 | [Firecrawl](https://www.firecrawl.dev) (hosted) | yes | Firecrawl API key |
| 3 | Firecrawl Local (`AI/ModelEngines/FirecrawlLocalService`) | no | its address and token |
| 4 | [Scrapy](https://scrapy.org), inside Armory | no | nothing |

An engine that is not configured is skipped. The next engine runs when one is unreachable, times out, rejects the key,
is out of quota, answers with an error or an unreadable reply, or answers with nothing. The chain stops when the page
itself answers 404 or 410 (Tavily does not report that status). The result's `message` names the engine that answered;
why an engine was passed over is in the server log. If none answers, the tool fails with one numbered error for `web`.

Each engine gets 30 seconds (60 for a crawl), no engine starts after 90 seconds, and none runs past 110, inside
Legion's 120 second tool limit. A crawl that returns pages ends the chain, finished or not.

## Safety and cost

`read`, `map` and `crawl` refuse any address that is not a public `http` or `https` address on port 80 or 443, before
an engine sees it. Scrapy is the only engine where this server opens the address itself: it runs in its own process
(`engines/scrapy_worker.py`) that checks every request and every name lookup again, obeys `robots.txt`, ignores proxy
variables, stays on the start site, and limits page size, count and depth. It does not run JavaScript.

Page text is capped at 24 KB (a crawl at 48 KB in total) and fenced as remote data (`services/untrusted.py`); search
snippets are cut to 600 characters. Tools never call an AI. Searches and reads run without asking in ember's Auto
approval and can use Tavily or Firecrawl credits; map and crawl always ask.

## Configuration

Set on the Settings page of Armory Admin; saved in Armory's database and used at once: the Tavily API key, the
Firecrawl API key, and the Firecrawl Local address and token. With none of them, read, map and crawl use Scrapy and
search fails as not configured.

Toggle: `"web"` in the Capabilities page (stored in `.data/armory/settings.db`).
