# pmpts - a Prompt Management CLI

Small CLI to manage VS Code prompt files (move/add/remove/list/rename/undo).

# Quick Start

Install as an isolated tool with uv

```bash
uv tool install --from git+https://github.com/andrader/pmpts pmpts
# check installation
pmpts --help
```
or with plain pip

```bash
pip install git+https://github.com/andrader/pmpts
pmpts --help
```

# Examples 

List all prompts:
```bash
pmpts list -v
```

Add a new prompt file to the centered repository:
```bash
pmpts add my-prompt.md
```

Rename a prompt:
```bash
pmpts rename old-name new-name
```
