import UniversalProvider from '@walletconnect/universal-provider';
import { type CaipNetwork, type ChainNamespace } from '@reown/appkit-common';
import { type ChainAdapter, type ConnectMethod, type ConnectedWalletInfo, type ConnectorType, type EventsControllerState, type Features, type ModalControllerState, type OptionsControllerState, type PublicStateControllerState, type RouterControllerState, type SdkVersion, type SocialProvider, type ThemeControllerState, type UseAppKitAccountReturn, type UseAppKitNetworkReturn, type WalletFeature } from '@reown/appkit-core';
import { AccountController, AssetUtil, BlockchainApiController, ChainController, ConnectionController, ConnectorController, EnsController, OptionsController } from '@reown/appkit-core';
import { type W3mFrameTypes } from '@reown/appkit-wallet';
import type { AppKitNetwork } from '@reown/appkit/networks';
import type { AdapterBlueprint } from './adapters/ChainAdapterBlueprint.js';
import { type ProviderStoreUtilState } from './store/ProviderUtil.js';
import { UniversalAdapter as UniversalAdapterClient } from './universal-adapter/client.js';
import type { AppKitOptions } from './utils/TypesUtil.js';
declare global {
    interface Window {
        ethereum?: Record<string, unknown>;
    }
}
export { AccountController };
export interface OpenOptions {
    view: 'Account' | 'Connect' | 'Networks' | 'ApproveTransaction' | 'OnRampProviders' | 'ConnectingWalletConnectBasic' | 'Swap' | 'WhatIsAWallet' | 'WhatIsANetwork' | 'AllWallets' | 'WalletSend';
    uri?: string;
    namespace?: ChainNamespace;
}
type Adapters = Record<ChainNamespace, AdapterBlueprint>;
interface AppKitOptionsWithSdk extends AppKitOptions {
    sdkVersion: SdkVersion;
}
export declare class AppKit {
    private static instance?;
    activeAdapter?: AdapterBlueprint;
    options: AppKitOptions;
    adapters?: ChainAdapter[];
    activeChainNamespace?: ChainNamespace;
    chainNamespaces: ChainNamespace[];
    chainAdapters?: Adapters;
    universalAdapter?: UniversalAdapterClient;
    private universalProvider?;
    private connectionControllerClient?;
    private networkControllerClient?;
    private universalProviderInitPromise?;
    private authProvider?;
    private initPromise?;
    version: SdkVersion;
    adapter?: ChainAdapter;
    reportedAlertErrors: Record<string, boolean>;
    private caipNetworks?;
    private defaultCaipNetwork?;
    constructor(options: AppKitOptionsWithSdk);
    static getInstance(): AppKit | undefined;
    private initialize;
    private sendInitializeEvent;
    open(options?: OpenOptions): Promise<void>;
    close(): Promise<void>;
    setLoading(loading: ModalControllerState['loading']): void;
    getError(): string;
    getChainId(): string | number | undefined;
    switchNetwork(appKitNetwork: AppKitNetwork): Promise<void>;
    getWalletProvider(): unknown;
    getWalletProviderType(): ConnectorType | null | undefined;
    subscribeProviders(callback: (providers: ProviderStoreUtilState['providers']) => void): () => void;
    getThemeMode(): import("@reown/appkit-core").ThemeMode;
    getThemeVariables(): import("@reown/appkit-core").ThemeVariables;
    setThemeMode(themeMode: ThemeControllerState['themeMode']): void;
    setTermsConditionsUrl(termsConditionsUrl: string): void;
    setPrivacyPolicyUrl(privacyPolicyUrl: string): void;
    setThemeVariables(themeVariables: ThemeControllerState['themeVariables']): void;
    subscribeTheme(callback: (newState: ThemeControllerState) => void): () => void;
    getWalletInfo(): ConnectedWalletInfo | undefined;
    subscribeAccount(callback: (newState: UseAppKitAccountReturn) => void, namespace?: ChainNamespace): void;
    subscribeNetwork(callback: (newState: Omit<UseAppKitNetworkReturn, 'switchNetwork'>) => void): () => void;
    subscribeWalletInfo(callback: (newState?: ConnectedWalletInfo) => void): () => void;
    subscribeShouldUpdateToAddress(callback: (newState?: string) => void): void;
    subscribeCaipNetworkChange(callback: (newState?: CaipNetwork) => void): void;
    getState(): PublicStateControllerState;
    subscribeState(callback: (newState: PublicStateControllerState) => void): () => void;
    showErrorMessage(message: string): void;
    showSuccessMessage(message: string): void;
    getEvent(): {
        timestamp: number;
        reportedErrors: Record<string, boolean>;
        data: import("@reown/appkit-core").Event;
    };
    subscribeEvents(callback: (newEvent: EventsControllerState) => void): () => void;
    replace(route: RouterControllerState['view']): void;
    redirect(route: RouterControllerState['view']): void;
    popTransactionStack(cancel?: boolean): void;
    isOpen(): boolean;
    isTransactionStackEmpty(): boolean;
    setStatus: (typeof AccountController)['setStatus'];
    getIsConnectedState: () => boolean;
    setAllAccounts: (typeof AccountController)['setAllAccounts'];
    addAddressLabel: (typeof AccountController)['addAddressLabel'];
    removeAddressLabel: (typeof AccountController)['removeAddressLabel'];
    getCaipAddress: (chainNamespace?: ChainNamespace) => `eip155:${string}:${string}` | `eip155:${number}:${string}` | `solana:${string}:${string}` | `solana:${number}:${string}` | `polkadot:${string}:${string}` | `polkadot:${number}:${string}` | `bip122:${string}:${string}` | `bip122:${number}:${string}` | undefined;
    getAddressByChainNamespace: (chainNamespace: ChainNamespace) => string | undefined;
    getAddress: (chainNamespace?: ChainNamespace) => string | undefined;
    getProvider: <T>(namespace: ChainNamespace) => T | undefined;
    getProviderType: (namespace: ChainNamespace) => ConnectorType | undefined;
    getPreferredAccountType: () => W3mFrameTypes.AccountType;
    setCaipAddress: (typeof AccountController)['setCaipAddress'];
    setBalance: (typeof AccountController)['setBalance'];
    setProfileName: (typeof AccountController)['setProfileName'];
    setProfileImage: (typeof AccountController)['setProfileImage'];
    setUser: (typeof AccountController)['setUser'];
    resetAccount: (typeof AccountController)['resetAccount'];
    setCaipNetwork: (typeof ChainController)['setActiveCaipNetwork'];
    getCaipNetwork: (chainNamespace?: ChainNamespace) => CaipNetwork | undefined;
    getCaipNetworkId: <T extends number | string>() => T | undefined;
    getCaipNetworks: (namespace: ChainNamespace) => CaipNetwork[];
    getActiveChainNamespace: () => ChainNamespace | undefined;
    setRequestedCaipNetworks: (typeof ChainController)['setRequestedCaipNetworks'];
    getApprovedCaipNetworkIds: (typeof ChainController)['getAllApprovedCaipNetworkIds'];
    setApprovedCaipNetworksData: (typeof ChainController)['setApprovedCaipNetworksData'];
    resetNetwork: (typeof ChainController)['resetNetwork'];
    setConnectors: (typeof ConnectorController)['setConnectors'];
    addConnector: (typeof ConnectorController)['addConnector'];
    getConnectors: (typeof ConnectorController)['getConnectors'];
    resetWcConnection: (typeof ConnectionController)['resetWcConnection'];
    fetchIdentity: (typeof BlockchainApiController)['fetchIdentity'];
    setAddressExplorerUrl: (typeof AccountController)['setAddressExplorerUrl'];
    setSmartAccountDeployed: (typeof AccountController)['setSmartAccountDeployed'];
    setConnectedWalletInfo: (typeof AccountController)['setConnectedWalletInfo'];
    setSmartAccountEnabledNetworks: (typeof ChainController)['setSmartAccountEnabledNetworks'];
    setPreferredAccountType: (typeof AccountController)['setPreferredAccountType'];
    getReownName: (typeof EnsController)['getNamesForAddress'];
    setEIP6963Enabled: (typeof OptionsController)['setEIP6963Enabled'];
    setClientId: (typeof BlockchainApiController)['setClientId'];
    getConnectorImage: (typeof AssetUtil)['getConnectorImage'];
    handleUnsafeRPCRequest: () => void;
    updateFeatures(newFeatures: Partial<Features>): void;
    updateOptions(newOptions: Partial<OptionsControllerState>): void;
    setConnectMethodsOrder(connectMethodsOrder: ConnectMethod[]): void;
    setWalletFeaturesOrder(walletFeaturesOrder: WalletFeature[]): void;
    setCollapseWallets(collapseWallets: boolean): void;
    setSocialsOrder(socialsOrder: SocialProvider[]): void;
    disconnect(): Promise<void>;
    getConnectMethodsOrder(): ConnectMethod[];
    /**
     * Removes an adapter from the AppKit.
     * @param namespace - The namespace of the adapter to remove.
     */
    removeAdapter(namespace: ChainNamespace): void;
    /**
     * Adds an adapter to the AppKit.
     * @param adapter - The adapter instance.
     * @param networks - The list of networks that this adapter supports / uses.
     */
    addAdapter(adapter: ChainAdapter, networks: [AppKitNetwork, ...AppKitNetwork[]]): void;
    /**
     * Adds a network to an existing adapter in AppKit.
     * @param namespace - The chain namespace to add the network to (e.g. 'eip155', 'solana')
     * @param network - The network configuration to add
     * @throws Error if adapter for namespace doesn't exist
     */
    addNetwork(namespace: ChainNamespace, network: AppKitNetwork): void;
    /**
     * Removes a network from an existing adapter in AppKit.
     * @param namespace - The chain namespace the network belongs to
     * @param networkId - The network ID to remove
     * @throws Error if adapter for namespace doesn't exist or if removing last network
     */
    removeNetwork(namespace: ChainNamespace, networkId: string | number): void;
    private initializeOptionsController;
    private initializeThemeController;
    private initializeChainController;
    private initializeBlockchainApiController;
    private initControllers;
    private getDefaultMetaData;
    private setUnsupportedNetwork;
    private extendCaipNetwork;
    private extendCaipNetworks;
    private extendDefaultCaipNetwork;
    private createClients;
    private setupAuthConnectorListeners;
    private syncAuthConnector;
    private listenWalletConnect;
    private listenAdapter;
    private updateNativeBalance;
    private getChainsFromNamespaces;
    private syncWalletConnectAccount;
    private syncWalletConnectAccounts;
    private syncProvider;
    private syncAccount;
    private syncBalance;
    private syncConnectedWalletInfo;
    private syncIdentity;
    private syncReownName;
    private syncAdapterConnection;
    private syncNamespaceConnection;
    private syncExistingConnection;
    private getAdapter;
    private createUniversalProvider;
    private handleAlertError;
    private initializeUniversalAdapter;
    getUniversalProvider(): Promise<UniversalProvider | undefined>;
    private createAuthProvider;
    private createUniversalProviderForAdapter;
    private createAuthProviderForAdapter;
    private createAdapter;
    private createAdapters;
    private onConnectors;
    private initChainAdapter;
    private initChainAdapters;
    private getUnsupportedNetwork;
    private getDefaultNetwork;
    private injectModalUi;
    private checkExistingSocialConnection;
}
