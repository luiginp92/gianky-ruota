import { LitElement } from 'lit';
export declare class W3mUnsupportedChainView extends LitElement {
    static styles: import("lit").CSSResult;
    protected readonly swapUnsupportedChain: boolean | undefined;
    private unsubscribe;
    private disconecting;
    constructor();
    disconnectedCallback(): void;
    render(): import("lit").TemplateResult<1>;
    private descriptionTemplate;
    private networksTemplate;
    private onDisconnect;
    private onSwitchNetwork;
}
declare global {
    interface HTMLElementTagNameMap {
        'w3m-unsupported-chain-view': W3mUnsupportedChainView;
    }
}
