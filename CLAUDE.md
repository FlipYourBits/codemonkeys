# agentpipe

## Environment

- Python: `.venv/bin/python`
- Run tests: `.venv/bin/python -m pytest tests/ -x -q --no-header`

## Architecture
- Live by occam's razor (the simplest solution is usually the best), for example I don't want something so over engineered that a junior dev would look at it and be confused on how things work. It should be very obvious on how the code works and how to extend/modify/create a graph or node. 
- Each node has a single responsibility and never depends on another node.
- Graphs with a `__main__` block must use `argparse` for CLI argument parsing.
