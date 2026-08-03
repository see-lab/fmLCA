# Contributing to LCA-FMU

Thank you for your interest in contributing to LCA-FMU! This project is maintained by the SEE Lab at the University of Vermont.

## 🚀 Getting Started

### Prerequisites

- Python 3.9+ (tested through 3.13)
- Brightway 2.5 with ecoinvent database access
- Git for version control
- Familiarity with Life Cycle Assessment concepts

### Development Setup

1. Fork the repository on GitHub
2. Clone your fork:
   ```bash
   git clone https://github.com/YOUR-USERNAME/lca-fmu.git
   cd lca-fmu
   ```

3. Create a virtual environment:
   ```bash
   python -m venv venv
   source venv/bin/activate  # macOS/Linux
   # venv\Scripts\activate  # Windows
   ```

4. Install development dependencies:
   ```bash
   pip install -r requirements.txt
   ```

5. Create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## 📝 Code Guidelines

### Style Conventions

- Follow PEP 8 for Python code style
- Use meaningful variable and function names
- Add docstrings to all functions and classes
- Keep functions focused and modular

### Documentation

- Update relevant documentation in `docs/` for new features
- Add inline comments for complex logic
- Update README.md if adding major functionality
- Include examples for new features

### Testing

Before submitting a pull request, run all tests:

```bash
# Test FMU functionality (works on all platforms)
python tests/test_cumulative_fmu_direct.py

# Test LCIA methods
python tests/test_methods_format.py
python tests/test_methods_loader.py

# Test argument parsing
python tests/test_arg_parsing.py
```

### Commit Messages

Use clear, descriptive commit messages:
- ✅ `Add IMPACT World+ freshwater ecotoxicity methods`
- ✅ `Fix energy scaling in cumulative FMU calculation`
- ❌ `fixed bug`
- ❌ `updates`

## 🔬 What to Contribute

### High Priority

- **Additional cooling technologies**: Dry cooling towers, hybrid wet-dry systems
- **More energy storage systems**: Hydrogen storage, compressed air
- **Performance optimizations**: Faster method loading, caching strategies
- **Test coverage**: Unit tests for edge cases
- **Documentation improvements**: Tutorials, use case examples

### Medium Priority

- **Additional LCIA methods**: More impact categories, regional methods
- **Visualization improvements**: Better plots, interactive dashboards
- **CI/CD pipeline**: Automated testing, deployment workflows
- **Error handling**: Better error messages, validation

### Welcome Contributions

- Bug fixes
- Documentation clarifications
- Example scripts and use cases
- Performance benchmarks
- Integration with other tools

## 🐛 Reporting Issues

### Bug Reports

When reporting bugs, please include:

1. **Description**: Clear description of the issue
2. **Environment**: OS, Python version, package versions
3. **Steps to reproduce**: Minimal code to reproduce the issue
4. **Expected behavior**: What should happen
5. **Actual behavior**: What actually happens
6. **Error messages**: Full error traceback

### Feature Requests

For feature requests, please provide:

1. **Use case**: Why is this feature needed?
2. **Proposed solution**: How should it work?
3. **Alternatives considered**: Other approaches you've thought about
4. **Additional context**: Examples, references, mock-ups

## 🔍 Pull Request Process

1. **Ensure tests pass**: Run all tests before submitting
2. **Update documentation**: Reflect changes in relevant docs
3. **Add tests**: Include tests for new functionality
4. **Keep changes focused**: One feature/fix per PR
5. **Describe changes**: Clear PR description with context

### PR Checklist

- [ ] Code follows project style guidelines
- [ ] All tests pass successfully
- [ ] New features have corresponding tests
- [ ] Documentation is updated
- [ ] Commit messages are clear and descriptive
- [ ] No merge conflicts with main branch

## 🏗️ Development Notes

### Key Design Principles

1. **Energy metadata system**: Use `amount_ref` for dynamic energy scaling
2. **IPCC 2021 compliance**: Prioritize IPCC 2021 methods for climate change
3. **Brightway integration**: Maintain compatibility with Brightway 2.5 ecosystem
4. **Platform compatibility**: FMU binaries for Linux/Windows, Python fallback for macOS

### Important Files

- `src/lca_engine.py`: Main LCA analysis engine
- `scripts/create_fmu.py`: FMU generation logic
- `data/methods/iw_damages.json`: IMPACT World+ damage indicators
- `tests/test_cumulative_fmu_direct.py`: FMU validation (macOS compatible)

### Testing Strategy

- **Unit tests**: Individual function testing
- **Integration tests**: Full workflow validation
- **Validation tests**: Compare against SimaPro, literature values
- **Platform tests**: Ensure macOS Python fallback works

## 📚 Resources

- **Brightway Documentation**: https://docs.brightway.dev/
- **IMPACT World+ Methods**: http://www.impactworldplus.org/
- **FMI Standard**: https://fmi-standard.org/
- **Ecoinvent Database**: https://ecoinvent.org/

## 💬 Getting Help

- Open an issue for questions
- Check existing documentation in `docs/`
- Review closed issues and PRs for similar problems
- Contact maintainers through the SEE Lab

By contributing, you agree that your contributions will be licensed under the BSD 3-Clause License.
---

Thank you for contributing to LCA-FMU! Your efforts help advance sustainable energy systems research. 🌱
