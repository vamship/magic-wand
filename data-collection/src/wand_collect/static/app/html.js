// htm bound to Preact's createElement, so pages write markup as templates.

import { h } from "preact";
import htm from "htm";

export const html = htm.bind(h);
