import {Injectable} from '@angular/core';
import {FabricSettings} from '../_model/fabric-settings';
import {Fabric} from '../_model/fabric';

@Injectable({
    providedIn: 'root'
})

export class FabricService {
    fabricSettings: FabricSettings;
    fabric: Fabric;

    constructor() {
        this.fabric = new Fabric()
        this.fabricSettings = new FabricSettings()
    }
}