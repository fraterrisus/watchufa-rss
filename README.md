# WatchUFA RSS Builder

Builds an RSS feed for the league news page of the [UFA](https://watchufa.com/league/news).

## Installation

1. Install [pyenv](https://github.com/pyenv/pyenv), if you don't already have it, and run `pyenv install 3.12`. 
2. Install [pipenv](https://pipenv.pypa.io/en/latest/), if you don't already have it.
3. `cd watchufa-rss`
4. `pipenv install`

## Using

`pipenv run rss` will run the core script.

It runs a HEAD request and attempts to determine if the content has changed by saving the Etag in
a local file `.etag` and comparing it to what comes back from the server. If the server indicates
no change, the script exits with status 201 (the HTTP status for Not Modified). Otherwise, it will
run a full GET request, attempt to build a (new) RSS file at `watchufa.rss`, and exit with status 0.

You should then copy the RSS file into a web root somewhere where it can be served.