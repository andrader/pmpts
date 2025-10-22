# pmpts - a Prompt Management CLI

Small CLI to manage VS Code prompt files (move/add/remove/list/rename/undo).

Install / Development
---------------------

Run it with uvx
```bash
uvx pmpts --help
```

or install as an isolated tool with uv
```bash
uv tool install pmpts
# then use it
pmpts --help
```
or with plain pip

```bash
pip install pmpts
```

The console script `pmpts` will be available in your environment. Examples:

```bash
pmpts list -v
pmpts add ~/Downloads/my.md
pmpts rename old-name new-name
```

