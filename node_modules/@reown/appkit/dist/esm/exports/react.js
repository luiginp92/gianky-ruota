import { CoreHelperUtil } from '@reown/appkit-core';
import { useAppKitNetworkCore } from '@reown/appkit-core/react';
import { AppKit } from '../src/client.js';
import { getAppKit } from '../src/library/react/index.js';
import { PACKAGE_VERSION } from './constants.js';
// -- Views ------------------------------------------------------------
export * from '@reown/appkit-scaffold-ui';
// -- Hooks ------------------------------------------------------------
export * from '../src/library/react/index.js';
// -- Utils & Other -----------------------------------------------------
export * from '../src/utils/index.js';
export { CoreHelperUtil, AccountController } from '@reown/appkit-core';
export let modal = undefined;
export function createAppKit(options) {
    if (!modal) {
        modal = new AppKit({
            ...options,
            sdkVersion: CoreHelperUtil.generateSdkVersion(options.adapters ?? [], 'react', PACKAGE_VERSION)
        });
        getAppKit(modal);
    }
    return modal;
}
export { AppKit };
// -- Hooks ------------------------------------------------------------
export * from '../src/library/react/index.js';
export function useAppKitNetwork() {
    const { caipNetwork, caipNetworkId, chainId } = useAppKitNetworkCore();
    function switchNetwork(network) {
        modal?.switchNetwork(network);
    }
    return {
        caipNetwork,
        caipNetworkId,
        chainId,
        switchNetwork
    };
}
export { useAppKitAccount } from '@reown/appkit-core/react';
//# sourceMappingURL=react.js.map