import { LitElement } from 'lit';
export declare class W3mAccountView extends LitElement {
    private unsubscribe;
    namespace: import("@reown/appkit-common").ChainNamespace | undefined;
    constructor();
    render(): import("lit").TemplateResult<1> | null;
    private walletFeaturesTemplate;
    private defaultTemplate;
}
declare global {
    interface HTMLElementTagNameMap {
        'w3m-account-view': W3mAccountView;
    }
}
