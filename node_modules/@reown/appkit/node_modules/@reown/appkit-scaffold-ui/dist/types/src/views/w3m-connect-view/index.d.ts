import { LitElement } from 'lit';
export declare class W3mConnectView extends LitElement {
    static styles: import("lit").CSSResult;
    private unsubscribe;
    private connectors;
    private authConnector;
    private features;
    private enableWallets;
    private noAdapters;
    private walletGuide;
    private checked;
    private isEmailEnabled;
    private isSocialEnabled;
    private isAuthEnabled;
    private resizeObserver?;
    constructor();
    disconnectedCallback(): void;
    firstUpdated(): void;
    render(): import("lit").TemplateResult<1>;
    private setEmailAndSocialEnableCheck;
    private checkIfAuthEnabled;
    private renderConnectMethod;
    private checkMethodEnabled;
    private checkIsThereNextMethod;
    private separatorTemplate;
    private emailTemplate;
    private socialListTemplate;
    private walletListTemplate;
    private guideTemplate;
    private legalCheckboxTemplate;
    private handleConnectListScroll;
    private onContinueWalletClick;
    private onCheckboxChange;
}
declare global {
    interface HTMLElementTagNameMap {
        'w3m-connect-view': W3mConnectView;
    }
}
