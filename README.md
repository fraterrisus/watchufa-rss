# WatchUFA RSS Builder

Builds an RSS feed for the league news page of the [UFA](https://watchufa.com/league/news).

## Installation

1. Install [pyenv](https://github.com/pyenv/pyenv), if you don't already have it, and run `pyenv install 3.12`. 
2. Install [pipenv](https://pipenv.pypa.io/en/latest/), if you don't already have it.
3. `cd watchufa-rss`
4. `pipenv install`
5. `pipenv run rss`

That should generate a file `watchufa.rss` in the current working directory, which you can
then copy wherever you want to serve it from.