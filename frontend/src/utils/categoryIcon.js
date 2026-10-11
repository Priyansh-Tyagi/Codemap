import {
  Component, Cog, SlidersHorizontal, Database, Layers, Route, Webhook, PanelTop,
  Settings2, Wrench, FlaskConical, Braces, DatabaseZap, Terminal, ShieldCheck, File,
} from "lucide-react";

/** A glyph per architecture category, so a node says what it IS at a glance
 * (shape + colour) instead of relying on colour alone. */
const ICONS = {
  Component, Service: Cog, Controller: SlidersHorizontal, Model: Database,
  Middleware: Layers, Route, Hook: Webhook, Page: PanelTop, Config: Settings2,
  Util: Wrench, Test: FlaskConical, Serializer: Braces, Migration: DatabaseZap,
  Command: Terminal, Admin: ShieldCheck,
};

export function iconForCategory(architectureType) {
  return ICONS[architectureType] ?? File;
}
