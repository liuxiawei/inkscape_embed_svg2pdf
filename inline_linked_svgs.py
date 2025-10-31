#!/usr/bin/env python3
"""
Recursively inlines linked SVG files (including nested ones), converts all to Plain SVG,
and exports to PDF using Inkscape. Fixes text misalignment.
"""

import argparse
import subprocess
import logging
from pathlib import Path
from lxml import etree
from urllib.parse import urlparse, unquote
import os


SVG_NS = "http://www.w3.org/2000/svg"
XLINK_NS = "http://www.w3.org/1999/xlink"
NSMAP = {"svg": SVG_NS, "xlink": XLINK_NS}

etree.register_namespace("svg", SVG_NS)
etree.register_namespace("xlink", XLINK_NS)

logger = logging.getLogger(__name__)


def make_absolute_href(href: str, base_path: Path) -> str:
    """Converts relative href to absolute file URI."""
    if (
        href.startswith("data:")
        or href.startswith("http:")
        or href.startswith("https:")
        or href.startswith("file:///")
        or href.startswith("file:////")
        or Path(href).is_absolute()
    ):
        return href

    abs_path = (base_path / href).resolve()
    if not abs_path.is_file():
        raise FileNotFoundError(f"File {abs_path} doesn't exist!")
    return "file:///" + abs_path.as_posix()


def extract_path_from_href(href: str) -> Path:
    """Extract local file path from URI."""
    if href.startswith("file://"):
        parsed = urlparse(href)
        path = unquote(parsed.path)
        if os.name == "nt" and len(path) > 2 and path[1] == ":" and path.startswith("/"):
            path = path[1:]  # Fix Windows path: /C:/path → C:/path
        return Path(path)
    return Path(href).resolve()


def convert_to_plain_svg(svg_path: Path) -> Path:
    """
    Convert any SVG (Inkscape or not) to Plain SVG using Inkscape.
    Returns the path to the plain SVG.
    """
    logger.info(f"Converting to Plain SVG: {svg_path.name}")
    plain_svg_path = svg_path.with_name(f"plain_{svg_path.name}")

    result = subprocess.run(
        [
            "inkscape",
            str(svg_path),
            "--export-plain-svg",
            f"--export-filename={str(plain_svg_path)}",
            "--vacuum-defs",  # ← 新增：精简 defs，减少冗余
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        logger.error(f"Inkscape failed to convert:\n{result.stderr.decode()}")
        raise RuntimeError("Inkscape export-plain-svg failed.")

    if not plain_svg_path.exists() or plain_svg_path.stat().st_size == 0:
        raise RuntimeError("Plain SVG output is empty or missing.")

    logger.info(f"Converted to: {plain_svg_path}")
    return plain_svg_path


def ensure_defs_parent(root: etree.Element) -> etree.Element:
    """Ensure the root has a <defs> element and return it."""
    defs = root.find("svg:defs", namespaces=NSMAP)
    if defs is None:
        defs = etree.Element(f"{{{SVG_NS}}}defs")
        root.insert(0, defs)
    return defs


def process_svg_tree_recursive(
    root: etree.Element,
    base_dir: Path,
    parser,
    main_defs: etree.Element,
    depth: int = 0,
    max_depth: int = 10,
) -> None:
    """Recursively inline linked SVGs after converting them to Plain SVG."""
    if depth > max_depth:
        logger.warning(f"Max recursion depth ({max_depth}) exceeded. Stopping.")
        return

    href_attr = f"{{{XLINK_NS}}}href"
    images = root.xpath(".//svg:image", namespaces=NSMAP)

    for image in list(images):
        href = image.attrib.get(href_attr)
        if not href or not href.lower().endswith(".svg"):
            continue

        try:
            abs_href = make_absolute_href(href, base_dir)
            linked_path = extract_path_from_href(abs_href)
            if not linked_path.exists():
                logger.warning(f"Linked SVG not found: {linked_path}")
                continue

            logger.info(f"{'  ' * depth}Processing: {linked_path.name} (depth {depth})")

            # ✅ Step 1: Convert to Plain SVG first
            plain_linked_path = convert_to_plain_svg(linked_path)

            # ✅ Step 2: Parse the Plain SVG
            sub_tree = etree.parse(str(plain_linked_path), parser)
            sub_root = sub_tree.getroot()

            # Recursively inline nested SVGs inside this one
            process_svg_tree_recursive(
                sub_root, plain_linked_path.parent, parser, main_defs, depth + 1, max_depth
            )

            # Parse viewBox
            viewBox = sub_root.attrib.get("viewBox")
            if viewBox:
                parts = viewBox.strip().split()
                if len(parts) == 4:
                    min_x, min_y, vb_width, vb_height = map(float, parts)
                else:
                    min_x, min_y, vb_width, vb_height = 0, 0, 100, 100
                    logger.warning(f"Invalid viewBox in {plain_linked_path.name}")
            else:
                width_attr = sub_root.attrib.get("width", "100").replace("px", "")
                height_attr = sub_root.attrib.get("height", "100").replace("px", "")
                try:
                    vb_width = float(width_attr)
                    vb_height = float(height_attr)
                except ValueError:
                    vb_width = vb_height = 100
                min_x, min_y = 0, 0

            # Get image position and size
            x = float(image.attrib.get("x", "0"))
            y = float(image.attrib.get("y", "0"))
            width = float(image.attrib.get("width", str(vb_width)))
            height = float(image.attrib.get("height", str(vb_height)))

            scale_x = width / vb_width
            scale_y = height / vb_height

            # Critical: Correct transform order
            transform_parts = [
                f"translate({x},{y})",           # Target position
                f"scale({scale_x},{scale_y})",   # Scale to fit
                f"translate({-min_x},{-min_y})", # Compensate viewBox offset
            ]
            if "transform" in image.attrib:
                transform_parts.insert(0, image.attrib["transform"])
            total_transform = " ".join(transform_parts)

            # Create group with transform
            wrapper = etree.Element(f"{{{SVG_NS}}}g", attrib={"transform": total_transform})

            # Move all children, and merge <defs>
            for elem in list(sub_root):
                if elem.tag == f"{{{SVG_NS}}}defs":
                    for child in elem:
                        main_defs.append(child)
                else:
                    wrapper.append(elem)

            # Replace <image> with <g>
            image.getparent().replace(image, wrapper)

            # ✅ Clean up temporary plain SVG
            plain_linked_path.unlink(missing_ok=True)
            logger.info(f"Removed temporary plain SVG: {plain_linked_path}")

        except Exception as e:
            logger.error(f"Failed to process {linked_path}: {e}")
            continue


def inline_linked_vectors(svg_path: Path) -> Path:
    """Convert main SVG to Plain SVG, then recursively inline all linked SVGs."""
    logger.info("Converting main SVG to Plain SVG...")
    plain_main_path = convert_to_plain_svg(svg_path)

    parser = etree.XMLParser(remove_blank_text=True, strip_cdata=False)
    tree = etree.parse(str(plain_main_path), parser)
    root = tree.getroot()

    # Ensure main SVG has a <defs> container
    main_defs = ensure_defs_parent(root)

    # Convert relative hrefs to absolute (debugging aid)
    href_attr = f"{{{XLINK_NS}}}href"
    for image in root.xpath(".//svg:image", namespaces=NSMAP):
        href = image.attrib.get(href_attr)
        if not href:
            continue
        try:
            new_href = make_absolute_href(href, svg_path.parent)
            resolved_path = extract_path_from_href(new_href)
            if resolved_path.exists():
                image.attrib[href_attr] = new_href
                logger.info(f"Made path absolute: {new_href}")
            else:
                logger.warning(f"Linked file not found: {new_href}")
        except Exception as e:
            logger.warning(f"Invalid href {href}: {e}")

    # Recursively inline all SVGs
    logger.info("Starting recursive inlining of nested SVGs...")
    process_svg_tree_recursive(root, plain_main_path.parent, parser, main_defs, depth=0)

    # Write inlined SVG
    temp_output = svg_path.with_name(f"temp_inlined_{svg_path.name}")
    tree.write(
        str(temp_output),
        pretty_print=False,
        xml_declaration=True,
        encoding="UTF-8"
    )
    logger.info(f"Fully inlined SVG saved to: {temp_output}")

    # Clean up main plain SVG
    plain_main_path.unlink(missing_ok=True)
    logger.info(f"Removed temporary main plain SVG: {plain_main_path}")

    return temp_output


def export_to_pdf(svg_path: Path, pdf_path: Path, text_to_path: bool = False):
    """
    Export SVG to PDF using Inkscape.
    No --pdf-fonts (as requested).
    """
    logger.info(f"Exporting to PDF with Inkscape (text-to-path={text_to_path})...")
    cmd = [
        "inkscape",
        str(svg_path),
        "--export-type=pdf",
        f"--export-filename={str(pdf_path)}"
    ]
    if text_to_path:
        cmd.append("--export-text-to-path")

    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    if result.returncode != 0:
        logger.error(f"Inkscape export failed:\n{result.stderr.decode()}")
        raise RuntimeError("Inkscape export failed.")
    logger.info(f"Exported successfully to: {pdf_path}")


def main():
    parser = argparse.ArgumentParser(
        description="Inline linked SVGs (after converting all to Plain SVG) and export to PDF."
    )
    parser.add_argument("input_svg", type=Path, help="Input SVG file")
    parser.add_argument("output_pdf", type=Path, help="Output PDF file")
    parser.add_argument("--verbose", action="store_true", help="Enable debug logging")
    parser.add_argument("--keep-temp", action="store_true", help="Keep temporary inlined SVG")
    parser.add_argument("--text-to-path", action="store_true", help="Convert text to paths")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    input_svg = args.input_svg.resolve()
    if not input_svg.exists():
        logger.error(f"Input SVG not found: {input_svg}")
        raise SystemExit(1)

    logger.info(f"Processing: {input_svg}")

    # Step 1: Convert and inline all SVGs
    inlined_svg_path = inline_linked_vectors(input_svg)

    # Step 2: Export to PDF
    try:
        export_to_pdf(inlined_svg_path, args.output_pdf, text_to_path=args.text_to_path)
    finally:
        if not args.keep_temp:
            inlined_svg_path.unlink(missing_ok=True)
            logger.info(f"Removed temporary inlined SVG: {inlined_svg_path}")


if __name__ == "__main__":
    main() 
