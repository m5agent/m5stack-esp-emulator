// Derived from MarsTechHAN/sticks3.js @ 974ebaa7ff35ad0ed9079211ef21b020cf0b7bcb; upstream package SPDX declaration: MIT.
// Preserve licenses/sticks3-upstream-package.json and THIRD_PARTY_NOTICES.md with this source.
import { ComponentHost } from './ComponentHost.js';

/**
 * A pluggable expansion module (Hat, Grove unit, …).
 *
 * `static meta.connector` names the connector standard it mates with (e.g.
 * `"m5.hat2"`, `"grove"`); a `Port` only accepts modules whose connector
 * matches. The module is modelled in the **port frame**:
 *
 *   origin  = centre of the port's mating face
 *   +Y      = out of the host (the direction the module extends)
 *   +Z      = towards the host's front (screen side)
 *
 * Its components are addressed through the port: `device.get('hat/matrix')`.
 * While plugged in, `module.attachedTo` is the Port and `module.parentHost` its host.
 */
export class Module extends ComponentHost {
  static meta = { id: 'module', name: 'Module', connector: null };

  get attached() {
    return !!this.attachedTo;
  }

  /** Optional hooks */
  onAttach(/* port */) {}
  onDetach(/* port */) {}
}
