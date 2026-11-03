//! Color parsing, naming and contrast helpers.

use serde::Serialize;

use crate::css3::CSS3;

/// An sRGB color.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct Rgb(pub u8, pub u8, pub u8);

impl Rgb {
    /// Parse `#rrggbb` or `rrggbb` (case-insensitive, surrounding whitespace allowed).
    pub fn parse(value: &str) -> Option<Self> {
        let value = value.trim();
        let hex = value.strip_prefix('#').unwrap_or(value);
        if hex.len() != 6 || !hex.bytes().all(|b| b.is_ascii_hexdigit()) {
            return None;
        }
        let channel = |i: usize| u8::from_str_radix(&hex[i..i + 2], 16).ok();
        Some(Self(channel(0)?, channel(2)?, channel(4)?))
    }

    /// Lowercase `#rrggbb`.
    pub fn hex(self) -> String {
        format!("#{:02x}{:02x}{:02x}", self.0, self.1, self.2)
    }

    /// A random shade of blue: R 0-100, G 0-200, B 150-255.
    pub fn random_blue() -> Self {
        Self(
            rand::random_range(0..=100),
            rand::random_range(0..=200),
            rand::random_range(150..=255),
        )
    }

    fn unit(self) -> (f64, f64, f64) {
        (
            f64::from(self.0) / 255.0,
            f64::from(self.1) / 255.0,
            f64::from(self.2) / 255.0,
        )
    }
}

/// Everything the templates show about a color.
#[derive(Clone, Debug, Serialize)]
pub struct ColorDetails {
    pub hex: String,
    pub descriptive_name: String,
    pub css_name: String,
    pub css_display_name: String,
    pub combined_name: String,
    /// Text color (dark or light) with the best contrast on this color.
    pub ink: &'static str,
}

impl ColorDetails {
    pub fn new(color: Rgb) -> Self {
        let descriptive_name = describe(color);
        let (css_name, exact) = nearest_css3(color);
        let css_display_name = if exact {
            css_name.to_owned()
        } else {
            format!("~ {css_name}")
        };
        Self {
            hex: color.hex(),
            combined_name: format!("{descriptive_name} / {css_display_name}"),
            descriptive_name,
            css_name: css_name.to_owned(),
            css_display_name,
            ink: ink(color),
        }
    }
}

/// Nearest CSS3 named color by Euclidean RGB distance, and whether it is exact.
pub fn nearest_css3(color: Rgb) -> (&'static str, bool) {
    let distance = |&(r, g, b, _): &(u8, u8, u8, &str)| {
        let d = |a: u8, b: u8| (i32::from(a) - i32::from(b)).pow(2);
        d(r, color.0) + d(g, color.1) + d(b, color.2)
    };
    // `min_by_key` keeps the first of equal elements, like the original table walk.
    let best = CSS3
        .iter()
        .min_by_key(|entry| distance(entry))
        .expect("CSS3 table is not empty");
    (best.3, distance(best) == 0)
}

/// Python's `colorsys.rgb_to_hls`.
fn rgb_to_hls(color: Rgb) -> (f64, f64, f64) {
    let (r, g, b) = color.unit();
    let max = r.max(g).max(b);
    let min = r.min(g).min(b);
    let l = (min + max) / 2.0;
    if (max - min).abs() < f64::EPSILON {
        return (0.0, l, 0.0);
    }
    let span = max - min;
    let s = if l <= 0.5 {
        span / (max + min)
    } else {
        span / (2.0 - max - min)
    };
    let (rc, gc, bc) = ((max - r) / span, (max - g) / span, (max - b) / span);
    #[allow(clippy::float_cmp)]
    let h = if r == max {
        bc - gc
    } else if g == max {
        2.0 + rc - bc
    } else {
        4.0 + gc - rc
    };
    ((h / 6.0).rem_euclid(1.0), l, s)
}

/// A human description such as "Vivid Dark Azure".
pub fn describe(color: Rgb) -> String {
    const HUES: &[(f64, &str)] = &[
        (15.0, "Red"),
        (45.0, "Orange"),
        (70.0, "Golden Yellow"),
        (100.0, "Lime"),
        (135.0, "Green"),
        (165.0, "Spring Green"),
        (190.0, "Teal"),
        (215.0, "Cyan"),
        (245.0, "Azure"),
        (275.0, "Blue"),
        (305.0, "Indigo"),
        (330.0, "Violet"),
        (345.0, "Magenta"),
        (360.0, "Red"),
    ];

    let (hue, lightness, saturation) = rgb_to_hls(color);

    if saturation < 0.12 {
        return match lightness {
            l if l < 0.08 => "Near Black",
            l if l < 0.22 => "Very Dark Gray",
            l if l < 0.38 => "Dark Gray",
            l if l < 0.65 => "Neutral Gray",
            l if l < 0.85 => "Light Gray",
            _ => "Near White",
        }
        .to_owned();
    }

    let degrees = (hue * 360.0).rem_euclid(360.0);
    let hue_name = HUES
        .iter()
        .find(|(end, _)| degrees < *end)
        .map_or("Color", |(_, name)| name);

    let saturation_adj = match saturation {
        s if s < 0.28 => "Soft",
        s if s < 0.55 => "",
        s if s < 0.78 => "Vivid",
        _ => "Brilliant",
    };
    let lightness_adj = match lightness {
        l if l < 0.2 => "Deep",
        l if l < 0.35 => "Dark",
        l if l < 0.5 => "",
        l if l < 0.7 => "Light",
        _ => "Pale",
    };

    [saturation_adj, lightness_adj, hue_name]
        .into_iter()
        .filter(|part| !part.is_empty())
        .collect::<Vec<_>>()
        .join(" ")
}

/// Dark or light text color, whichever has the higher WCAG contrast.
pub fn ink(color: Rgb) -> &'static str {
    let linear = |c: f64| {
        if c <= 0.040_45 {
            c / 12.92
        } else {
            ((c + 0.055) / 1.055).powf(2.4)
        }
    };
    let (r, g, b) = color.unit();
    let luminance = 0.0722f64.mul_add(linear(b), 0.2126f64.mul_add(linear(r), 0.7152 * linear(g)));
    let contrast_light = 1.05 / (luminance + 0.05);
    let contrast_dark = (luminance + 0.05) / 0.05;
    if contrast_dark > contrast_light {
        "#0b1020"
    } else {
        "#ffffff"
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    /// Reference values produced by the original Python implementation.
    const VECTORS: &[(&str, &str, &str, &str)] = &[
        ("#0000ff", "Brilliant Light Azure", "Blue", "#ffffff"),
        ("#336699", "Cyan", "~ Steel Blue", "#ffffff"),
        ("#1a2b3c", "Deep Cyan", "~ Dark Slate Grey", "#ffffff"),
        (
            "#6495ed",
            "Brilliant Light Azure",
            "Cornflower Blue",
            "#0b1020",
        ),
        ("#ffffff", "Near White", "White", "#0b1020"),
        ("#000000", "Near Black", "Black", "#ffffff"),
        (
            "#1191fc",
            "Brilliant Light Cyan",
            "~ Dodger Blue",
            "#0b1020",
        ),
        ("#6110b6", "Brilliant Blue", "~ Indigo", "#ffffff"),
        (
            "#0f7ef7",
            "Brilliant Light Cyan",
            "~ Dodger Blue",
            "#0b1020",
        ),
        (
            "#3978e9",
            "Brilliant Light Azure",
            "~ Royal Blue",
            "#0b1020",
        ),
        ("#3035a2", "Azure", "~ Dark Slate Blue", "#ffffff"),
        ("#3e07c7", "Brilliant Blue", "~ Medium Blue", "#ffffff"),
    ];

    #[test]
    fn matches_python_reference() {
        for &(hex, descriptive, css, ink) in VECTORS {
            let details = ColorDetails::new(Rgb::parse(hex).unwrap());
            assert_eq!(details.descriptive_name, descriptive, "{hex}");
            assert_eq!(details.css_display_name, css, "{hex}");
            assert_eq!(details.ink, ink, "{hex}");
            assert_eq!(details.combined_name, format!("{descriptive} / {css}"));
        }
    }

    #[test]
    fn parses_hex() {
        assert_eq!(Rgb::parse("#0A0b0C"), Some(Rgb(10, 11, 12)));
        assert_eq!(Rgb::parse(" 0a0b0c "), Some(Rgb(10, 11, 12)));
        assert_eq!(Rgb(10, 11, 12).hex(), "#0a0b0c");
        for bad in ["", "#", "#12345", "#1234567", "#12345g", "invalid"] {
            assert_eq!(Rgb::parse(bad), None, "{bad}");
        }
    }

    #[test]
    fn random_shades_are_blue() {
        for _ in 0..500 {
            let Rgb(r, g, b) = Rgb::random_blue();
            assert!(r <= 100 && g <= 200 && b >= 150);
        }
    }
}
