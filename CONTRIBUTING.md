# Contributing to fmLCA

Thank you for your interest in contributing to fmLCA! This project is maintained by the SEE Lab at the University of Vermont.

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
   git clone https://github.com/YOUR-USERNAME/fmLCA.git
   cd fmLCA
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
# Run all tests 
python -m pytest tests/

```

### Commit Messages

Use clear, descriptive commit messages:
- ✅ `Add IMPACT World+ freshwater ecotoxicity methods`
- ✅ `Fix energy scaling in cumulative FMU calculation`
- ❌ `fixed bug`
- ❌ `updates`

## 🔬 What to Contribute

This is a young project with a small development team. We welcome all ideas and suggestions for new features, enhancements, example cases, and bug fixes. If you have ideas, please open a issue or email the PI, and we will get back to you at the earliest convenience. 

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

Thank you for contributing to fmLCA! Your efforts help advance sustainable energy systems research. 🌱
