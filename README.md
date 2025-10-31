# Inkscape linked SVG vector PDF Exporter

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](https://opensource.org/licenses/MIT)

A Python tool to **recursively inline linked SVG files**, and export to **vector PDF using Inkscape**.

---

## 🌟 Features

- ✅ **Recursively inlines** all `<image xlink:href="*.svg">` elements (including nested ones)
- ✅ Preserves scaling, positioning, and `viewBox` via correct transform order
- ✅ Merges `<defs>` to avoid duplicate symbols or gradients
- ✅ Fixes **text rendering issues** in exported PDFs (by optionally converting text to paths)
- ✅ Uses **Inkscape** under the hood — no need for extra dependencies like Cairo
- ✅ Clean output: minimizes whitespace and temporary files
- ✅ Supports deep nesting with configurable recursion limit
---

## 🙏 Example

```python
python inline_linked_svgs.py in.svg out.pdf --verbose --keep-temp
```

---

## 🙏 Acknowledgements

This project was inspired by and builds upon the work of the following open-source tools:

- [**rob-the-bot/inkscape-vectorize-export**](https://github.com/rob-the-bot/inkscape-vectorize-export)  
  For the core idea of inlining linked SVGs to preserve vector quality in PDF exports.

- [**pluvionauts/inkscape_manage_image_links**](https://github.com/pluvionauts/inkscape_manage_image_links)  
  For demonstrating how to manipulate SVG image links and work with Inkscape's extension system.

Thank you to both projects for paving the way in managing SVG references in Inkscape workflows.

