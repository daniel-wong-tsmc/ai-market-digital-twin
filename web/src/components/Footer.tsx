/**
 * Zone 5 -- the footer. Exactly the links the payload carries, in the order
 * given (mock lines 795-805). The mock also carries a "Design mock..."
 * fine-print line, but the schema has no field behind it
 * (`web/schema/dashboard.schema.json`'s `footerLink` is only `{label, href}`),
 * so it is not invented here.
 */
import type {FooterLink} from '../load';
import {Disclaimer} from './Disclaimer';

export interface FooterProps {
  links: FooterLink[];
}

export function Footer({links}: FooterProps) {
  return (
    <footer>
      <nav aria-label="Deeper pages">
        {links.map((link) => (
          <a href={link.href} key={link.href}>
            {link.label}
          </a>
        ))}
      </nav>
      {/*
        F124: the standing disclaimer, below the links rather than beside them.
        It is a notice about the whole site, not another place to go.
      */}
      <Disclaimer />
    </footer>
  );
}
