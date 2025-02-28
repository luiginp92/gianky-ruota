import { LitElement } from 'lit';
import { type ChainNamespace } from '@reown/appkit-common';
export declare class W3mAccountAuthButton extends LitElement {
    private unsubscribe;
    private socialProvider;
    private socialUsername;
    namespace: ChainNamespace | undefined;
    constructor();
    disconnectedCallback(): void;
    render(): import("lit").TemplateResult<1> | null;
    private onGoToUpdateEmail;
    private getAuthName;
}
declare global {
    interface HTMLElementTagNameMap {
        'w3m-account-auth-button': W3mAccountAuthButton;
    }
}
